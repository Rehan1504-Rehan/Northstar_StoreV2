from decimal import Decimal
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


def delete_stored_file(name: str) -> None:
    """Remove a file from the active storage backend, ignoring failures.

    Losing an orphaned file is never worth breaking a product save over, so
    every error here is swallowed deliberately.
    """
    if not name:
        return
    try:
        default_storage.delete(name)
    except Exception:  # pragma: no cover - defensive cleanup only
        pass


def generate_order_number() -> str:
    """Generate a short, human-friendly order identifier."""
    return uuid.uuid4().hex[:12].upper()


class MediaFile(models.Model):
    """The bytes of an uploaded file, kept in the database.

    Hosting platforms give a web service an ephemeral container filesystem, so
    an image written to ``MEDIA_ROOT`` disappears on the next deploy or restart
    while the product row keeps pointing at it. Storing the payload here means
    uploads survive exactly as long as the rest of the data.

    Rows are written and read through ``store.storage.DatabaseStorage`` rather
    than directly.
    """

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Storage key, e.g. products/2026/09/lamp.webp",
    )
    content = models.BinaryField(help_text="Raw file bytes.")
    content_type = models.CharField(max_length=120, blank=True, default="")
    size = models.PositiveIntegerField(default=0, help_text="Size in bytes.")
    checksum = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="SHA-256 of the content; also used as the HTTP ETag.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Media file"
        verbose_name_plural = "Media files"

    def __str__(self) -> str:
        return self.name

    @property
    def data(self) -> bytes:
        """Content as ``bytes`` (PostgreSQL hands back a ``memoryview``)."""
        return bytes(self.content) if self.content is not None else b""


class Category(models.Model):
    """A simple product category managed from Django Admin."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Categories"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "category"
            candidate = base_slug
            counter = 2
            while Category.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = candidate
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("store:category_products", args=[self.slug])


class Product(models.Model):
    """A product that customers can browse and purchase."""

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField()
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    discount_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    image = models.ImageField(upload_to="products/%Y/%m/", blank=True, null=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # The default ordering above is a bare ``ORDER BY created_at DESC``
            # (admin changelist, "newest" listings); the composite indexes below
            # cannot serve it because ``available``/``category`` lead them.
            models.Index(fields=["-created_at"]),
            models.Index(fields=["available", "-created_at"]),
            models.Index(fields=["category", "-created_at"]),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        super().clean()
        if (
            self.discount_price is not None
            and self.price is not None
            and self.discount_price >= self.price
        ):
            raise ValidationError(
                {"discount_price": "The discount price must be lower than the regular price."}
            )

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "product"
            candidate = base_slug
            counter = 2
            while Product.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = candidate

        # Remember the stored file this product used before the save so a
        # replaced image does not linger in storage forever.
        previous_image = ""
        if self.pk:
            previous_image = (
                Product.objects.filter(pk=self.pk)
                .values_list("image", flat=True)
                .first()
                or ""
            )

        result = super().save(*args, **kwargs)

        current_image = self.image.name or ""
        if previous_image and previous_image != current_image:
            delete_stored_file(previous_image)
        return result

    @property
    def stock(self):
        """A friendly alias for code that calls the quantity simply ``stock``."""
        return self.stock_quantity

    @stock.setter
    def stock(self, value):
        self.stock_quantity = value

    def get_price(self) -> Decimal:
        return self.discount_price or self.price

    @property
    def has_discount(self) -> bool:
        return self.discount_price is not None

    @property
    def is_in_stock(self) -> bool:
        return self.available and self.stock_quantity > 0

    def get_absolute_url(self):
        return reverse("store:product_detail", args=[self.slug])


@receiver(post_delete, sender=Product)
def delete_product_image(sender, instance, **kwargs):
    """Drop the stored image when its product is deleted."""
    delete_stored_file(instance.image.name if instance.image else "")


class Cart(models.Model):
    """One persistent cart per authenticated customer."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Cart for {self.user.get_username()}"

    def total(self) -> Decimal:
        return sum((item.subtotal for item in self.items.select_related("product")), Decimal("0.00"))

    def item_count(self) -> int:
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    date_added = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date_added"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="unique_cart_product")
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.product.name}"

    @property
    def subtotal(self) -> Decimal:
        return self.product.get_price() * self.quantity


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    order_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        default=generate_order_number,
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    shipping_address = models.TextField()
    phone_number = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # The window in which an order can still be called off. Once a parcel has
    # been handed to the carrier (shipped or delivered) cancelling would strand
    # it in transit, so customers are pointed at the returns process instead.
    CANCELLABLE_STATUSES = (Status.PENDING, Status.PROCESSING)

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the order was cancelled; empty while it is still live.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Order {self.order_number}"

    def get_absolute_url(self):
        return reverse("store:order_detail", args=[self.order_number])

    @property
    def can_cancel(self) -> bool:
        """True while the customer (or staff) may still call this order off."""
        return self.status in self.CANCELLABLE_STATUSES

    @property
    def is_cancelled(self) -> bool:
        return self.status == self.Status.CANCELLED

    def cancel(self, *, restock: bool = True) -> bool:
        """Cancel the order and put its items back on the shelf.

        Returns ``True`` when this call is the one that cancelled the order,
        and ``False`` when it had already been cancelled or has moved past the
        cancellable window. Calling it twice is therefore safe: the second call
        reports ``False`` and never restocks a second time.

        The whole thing runs in one locked transaction, so a customer clicking
        the button twice, or staff cancelling while the customer does, cannot
        double the returned stock or race with a checkout selling the same
        units.
        """
        with transaction.atomic():
            # Re-read the row under a lock: the instance the caller holds may
            # be stale, and the status check has to happen inside the lock to
            # be worth anything.
            order = Order.objects.select_for_update().get(pk=self.pk)
            if order.status not in self.CANCELLABLE_STATUSES:
                return False

            if restock:
                self._restock(order)

            order.status = self.Status.CANCELLED
            order.cancelled_at = timezone.now()
            order.save(update_fields=["status", "cancelled_at", "updated_at"])

        # Keep the caller's copy in step with what was committed.
        self.status = order.status
        self.cancelled_at = order.cancelled_at
        return True

    @staticmethod
    def _restock(order: "Order") -> None:
        """Add each line's quantity back to its product, under row locks."""
        lines = list(order.items.select_related("product"))
        # Lock every product up front so a concurrent checkout cannot slip a
        # sale in between our read and our write.
        products = {
            product.pk: product
            for product in Product.objects.select_for_update().filter(
                pk__in=[line.product_id for line in lines if line.product_id]
            )
        }
        for line in lines:
            product = products.get(line.product_id)
            if product is None:
                # The catalog entry was deleted later (OrderItem.product is
                # SET_NULL), so there is no inventory to return the units to.
                continue
            was_sold_out = product.stock_quantity == 0
            product.stock_quantity += line.quantity
            if was_sold_out and not product.available:
                # Checkout switches a product off once it sells out; undoing
                # that here puts it back on the shelf. A product an admin
                # switched off by hand while it still had stock is left alone.
                product.available = True
            product.save(update_fields=["stock_quantity", "available", "updated_at"])


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # SET_NULL keeps an old order readable if an admin removes the catalog item.
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    product_name = models.CharField(max_length=200, blank=True, default="")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    # This is intentionally a snapshot, not a live reference to Product.price.
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.product_name}"

    @property
    def price_at_purchase(self) -> Decimal:
        """Readable alias documenting the historical-price behavior."""
        return self.price

    @property
    def line_total(self) -> Decimal:
        # Django Admin renders one blank inline row as the template for "add
        # another", and that row has no figures yet. Returning zero keeps the
        # order and order-item pages openable instead of raising TypeError on
        # ``None * None``.
        if self.price is None or self.quantity is None:
            return Decimal("0.00")
        return self.price * self.quantity
