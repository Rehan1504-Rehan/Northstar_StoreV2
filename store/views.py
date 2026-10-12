from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import File
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, FloatField, Prefetch, Q, Value
from django.db.models.functions import Coalesce
from django.http import Http404, HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST
from django.views.static import serve as static_serve
from django.utils.cache import get_conditional_response
from django.utils.http import http_date, url_has_allowed_host_and_scheme

from .forms import CheckoutForm, LoginForm, ProfileForm, RegistrationForm
from .models import Cart, CartItem, Category, MediaFile, Order, OrderItem, Product
from .storage import normalize_name


class OutOfStockError(Exception):
    """Raised inside the checkout transaction when inventory is not sufficient."""


# Sort options offered on the shop, category and deals pages. The value is the
# URL parameter; orderings are applied after the effective-price annotation.
SORT_OPTIONS = (
    ("newest", "Newest arrivals"),
    ("popular", "Most popular"),
    ("price_asc", "Price: Low to High"),
    ("price_desc", "Price: High to Low"),
    ("discount", "Biggest discount"),
)

LISTING_PAGE_SIZE = 12


def _annotated_products():
    """Available products with the price they actually sell for attached.

    ``effective_price`` (discount price when present, else list price) drives
    the price range filter and price sorting without touching the stored data.
    """
    return (
        Product.objects.filter(available=True)
        .select_related("category")
        .annotate(
            effective_price=Coalesce(
                "discount_price",
                "price",
                output_field=DecimalField(max_digits=10, decimal_places=2),
            ),
            order_count=Count("order_items"),
            discount_fraction=ExpressionWrapper(
                (F("price") - Coalesce("discount_price", F("price"))) * 100.0 / F("price"),
                output_field=FloatField(),
            ),
        )
    )


def _parse_money(raw):
    """Parse a price filter value, returning ``None`` for anything odd."""
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    if value < 0 or value > Decimal("99999999"):
        return None
    return value


def _apply_listing_filters(request, products):
    """Apply search, price range, sale and availability filters from GET."""
    query = request.GET.get("q", "").strip()
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
        )

    min_price = _parse_money(request.GET.get("min_price", "").strip())
    max_price = _parse_money(request.GET.get("max_price", "").strip())
    if min_price is not None:
        products = products.filter(effective_price__gte=min_price)
    if max_price is not None:
        products = products.filter(effective_price__lte=max_price)
    if min_price is not None and max_price is not None and min_price > max_price:
        # Swap instead of showing an impossible empty range.
        min_price, max_price = max_price, min_price

    on_sale = request.GET.get("sale") == "1"
    if on_sale:
        products = products.filter(discount_price__isnull=False)

    # Storefront listings hide sold-out items unless the shopper asks to see
    # them; ``available=False`` products stay hidden either way (admin switch).
    stock_filter = request.GET.get("stock", "in")
    if stock_filter != "all":
        stock_filter = "in"
        products = products.filter(stock_quantity__gt=0)

    sort = request.GET.get("sort", "newest")
    if sort == "price_asc":
        products = products.order_by("effective_price", "-created_at")
    elif sort == "price_desc":
        products = products.order_by("-effective_price", "-created_at")
    elif sort == "popular":
        products = products.order_by("-order_count", "-created_at")
    elif sort == "discount":
        products = products.filter(discount_price__isnull=False).order_by(
            "-discount_fraction", "-created_at"
        )
    else:
        sort = "newest"
        products = products.order_by("-created_at")

    filters = {
        "query": query,
        "min_price": request.GET.get("min_price", "").strip() if min_price is not None else "",
        "max_price": request.GET.get("max_price", "").strip() if max_price is not None else "",
        "on_sale": on_sale,
        "stock_filter": stock_filter,
        "sort": sort,
    }
    return products, filters


def _sidebar_categories():
    return Category.objects.annotate(
        product_count=Count(
            "products",
            filter=Q(products__available=True, products__stock_quantity__gt=0),
        )
    ).order_by("name")


def _render_listing(request, listing_extra, base_products):
    """Shared listing pipeline: filter, sort, paginate, render."""
    products, filters = _apply_listing_filters(request, base_products)
    paginator = Paginator(products, LISTING_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    context = {
        "products": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "categories": _sidebar_categories(),
        "sort_options": SORT_OPTIONS,
        **filters,
        **listing_extra,
    }
    return render(request, "store/product_list.html", context)


def home(request: HttpRequest) -> HttpResponse:
    in_stock = Q(products__available=True, products__stock_quantity__gt=0)
    featured_products = Product.objects.filter(
        available=True, stock_quantity__gt=0
    ).select_related("category")[:8]
    # Every category that currently has stock gets the same homepage treatment
    # as All Products / Electronics / Gaming: a shop-by card plus a product
    # shelf. Empty categories stay off the storefront until they have items.
    categories = list(
        Category.objects.annotate(product_count=Count("products", filter=in_stock))
        .filter(product_count__gt=0)
        .order_by("name")
        .prefetch_related(
            Prefetch(
                "products",
                queryset=Product.objects.filter(available=True, stock_quantity__gt=0)
                .select_related("category"),
                to_attr="in_stock_products",
            )
        )
    )
    category_cards = []
    category_sections = []
    for category in categories:
        products = list(category.in_stock_products)
        sample = next((item for item in products if item.image), None)
        category_cards.append(
            {"category": category, "product_count": category.product_count, "sample": sample}
        )
        category_sections.append(
            {
                "category": category,
                "products": products[:8],
                "product_count": category.product_count,
            }
        )
    deal_products = Product.objects.filter(
        available=True, stock_quantity__gt=0, discount_price__isnull=False
    ).select_related("category")[:4]
    return render(
        request,
        "store/home.html",
        {
            "featured_products": featured_products,
            "category_cards": category_cards,
            "category_sections": category_sections,
            "deal_products": deal_products,
        },
    )


def product_list(request: HttpRequest) -> HttpResponse:
    return _render_listing(request, {"selected_category": None}, _annotated_products())


def category_products(request: HttpRequest, slug: str) -> HttpResponse:
    category = get_object_or_404(Category, slug=slug)
    products = _annotated_products().filter(category=category)
    return _render_listing(request, {"selected_category": category}, products)


def deals(request: HttpRequest) -> HttpResponse:
    products = _annotated_products().filter(discount_price__isnull=False)
    return _render_listing(
        request,
        {"selected_category": None, "deals_page": True},
        products,
    )


def product_detail(request: HttpRequest, slug: str) -> HttpResponse:
    product = get_object_or_404(
        Product.objects.select_related("category"),
        slug=slug,
        available=True,
    )
    related_products = (
        Product.objects.filter(
            category=product.category,
            available=True,
            stock_quantity__gt=0,
        )
        .exclude(pk=product.pk)
        .select_related("category")[:4]
    )
    return render(
        request,
        "store/product_detail.html",
        {"product": product, "related_products": related_products},
    )


@require_http_methods(["GET", "POST"])
def register_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("store:home")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your account was created. You can now sign in.")
        return redirect("store:login")
    return render(request, "store/register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("store:home")

    next_url = request.GET.get("next") or request.POST.get("next") or ""
    form = LoginForm(request=request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        if not form.cleaned_data.get("remember_me"):
            # Session-only cookie: signed out when the browser closes.
            request.session.set_expiry(0)
        messages.success(request, f"Welcome back, {form.get_user().get_username()}!")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("store:home")
    return render(request, "store/login.html", {"form": form, "next": next_url})


@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    """Sign out through a CSRF-protected POST form."""
    logout(request)
    messages.info(request, "You have been signed out safely.")
    return redirect("store:home")


@login_required
def profile(request: HttpRequest) -> HttpResponse:
    """The signed-in shopper's own account details.

    Everything shown comes from ``request.user`` — the authenticated Django
    user loaded fresh from the database — so no name is ever hard-coded.
    """
    return render(request, "store/profile.html")


@login_required
@require_http_methods(["GET", "POST"])
def profile_edit(request: HttpRequest) -> HttpResponse:
    """Let the signed-in shopper update their own account details."""
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile was updated successfully.")
        return redirect("store:profile")
    return render(request, "store/profile_edit.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def change_password(request: HttpRequest) -> HttpResponse:
    """Let the signed-in shopper change their own password.

    Uses Django's ``PasswordChangeForm`` and re-authenticates the session
    afterwards so the user stays signed in with the new password.
    """
    form = PasswordChangeForm(user=request.user, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        update_session_auth_hash(request, form.user)
        messages.success(request, "Your password was changed successfully.")
        return redirect("store:profile")
    return render(request, "store/change_password.html", {"form": form})


@login_required
def _get_user_cart(request: HttpRequest) -> Cart:
    cart, _ = Cart.objects.get_or_create(user=request.user)
    return cart


def _cart_totals(items):
    """Totals for the summary panel, including how much the discounts save."""
    total = sum((item.subtotal for item in items), Decimal("0.00"))
    regular_total = sum(
        (item.product.price * item.quantity for item in items), Decimal("0.00")
    )
    return {
        "cart_total": total,
        "cart_regular_total": regular_total,
        "cart_savings": regular_total - total,
    }


@login_required
def cart_view(request: HttpRequest) -> HttpResponse:
    cart = _get_user_cart(request)
    items = list(cart.items.select_related("product", "product__category").all())
    context = {"cart": cart, "items": items, **_cart_totals(items)}
    return render(request, "store/cart.html", context)


@require_POST
@login_required
def add_to_cart(request: HttpRequest, product_id: int) -> HttpResponse:
    product = get_object_or_404(Product, pk=product_id, available=True)
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 0

    if quantity < 1:
        messages.error(request, "Choose a quantity of at least one.")
        return redirect(product.get_absolute_url())
    if quantity > product.stock_quantity:
        messages.error(request, f"Only {product.stock_quantity} item(s) are currently in stock.")
        return redirect(product.get_absolute_url())

    cart = _get_user_cart(request)
    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={"quantity": quantity},
    )
    if not created:
        new_quantity = item.quantity + quantity
        if new_quantity > product.stock_quantity:
            messages.error(
                request,
                f"Your cart cannot contain more than {product.stock_quantity} of this product.",
            )
            return redirect(product.get_absolute_url())
        item.quantity = new_quantity
        item.save(update_fields=["quantity"])
    cart.save(update_fields=["updated_at"])
    messages.success(request, f"{product.name} was added to your cart.")
    if request.POST.get("buy_now") == "1":
        return redirect("store:checkout")
    return redirect("store:cart")


@require_POST
@login_required
def update_cart(request: HttpRequest, item_id: int) -> HttpResponse:
    item = get_object_or_404(
        CartItem.objects.select_related("product"),
        pk=item_id,
        cart__user=request.user,
    )
    try:
        quantity = int(request.POST.get("quantity", 0))
    except (TypeError, ValueError):
        quantity = 0

    if quantity <= 0:
        item.delete()
        messages.info(request, f"{item.product.name} was removed from your cart.")
    elif not item.product.available:
        messages.error(request, f"{item.product.name} is no longer available.")
    elif quantity > item.product.stock_quantity:
        messages.error(
            request,
            f"Only {item.product.stock_quantity} item(s) of {item.product.name} are in stock.",
        )
    else:
        item.quantity = quantity
        item.save(update_fields=["quantity"])
        item.cart.save(update_fields=["updated_at"])
        messages.success(request, "Your cart was updated.")
    return redirect("store:cart")


@require_POST
@login_required
def remove_from_cart(request: HttpRequest, item_id: int) -> HttpResponse:
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    name = item.product.name
    item.delete()
    messages.info(request, f"{name} was removed from your cart.")
    return redirect("store:cart")


@login_required
def checkout(request: HttpRequest) -> HttpResponse:
    cart = _get_user_cart(request)
    current_items = list(cart.items.select_related("product").all())
    if not current_items:
        messages.info(request, "Your cart is empty. Add a product before checking out.")
        return redirect("store:product_list")

    form = CheckoutForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                # Lock both the cart rows and each product row. This prevents two
                # simultaneous checkouts from selling the same inventory.
                locked_cart = Cart.objects.select_for_update().get(pk=cart.pk)
                locked_items = list(
                    CartItem.objects.select_for_update()
                    .filter(cart=locked_cart)
                    .select_related("product")
                )
                if not locked_items:
                    raise OutOfStockError("Your cart is empty. Please add an item and try again.")

                order_lines = []
                order_total = Decimal("0.00")
                for cart_item in locked_items:
                    product = Product.objects.select_for_update().get(pk=cart_item.product_id)
                    if not product.available:
                        raise OutOfStockError(f"{product.name} is no longer available.")
                    if cart_item.quantity > product.stock_quantity:
                        raise OutOfStockError(
                            f"Only {product.stock_quantity} of {product.name} remain in stock."
                        )
                    purchase_price = product.get_price()
                    order_lines.append((product, cart_item.quantity, purchase_price))
                    order_total += purchase_price * cart_item.quantity

                order = Order.objects.create(
                    user=request.user,
                    total_amount=order_total,
                    shipping_address=form.cleaned_data["shipping_address"],
                    phone_number=form.cleaned_data["phone_number"],
                )
                for product, quantity, purchase_price in order_lines:
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        quantity=quantity,
                        price=purchase_price,
                    )
                    product.stock_quantity -= quantity
                    if product.stock_quantity == 0:
                        product.available = False
                    product.save(update_fields=["stock_quantity", "available", "updated_at"])
                CartItem.objects.filter(cart=locked_cart).delete()
                locked_cart.save(update_fields=["updated_at"])
        except OutOfStockError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f"Order {order.order_number} was placed successfully.")
            return redirect("store:order_detail", order_number=order.order_number)

    # Re-read items after a validation error so the order summary is current.
    items = list(cart.items.select_related("product", "product__category").all())
    context = {"form": form, "cart": cart, "items": items, **_cart_totals(items)}
    return render(request, "store/checkout.html", context)


@login_required
def order_list(request: HttpRequest) -> HttpResponse:
    orders = Order.objects.filter(user=request.user).prefetch_related("items")
    return render(request, "store/order_list.html", {"orders": orders})


@login_required
def order_detail(request: HttpRequest, order_number: str) -> HttpResponse:
    order = get_object_or_404(
        Order.objects.prefetch_related("items__product"),
        order_number=order_number,
        user=request.user,
    )
    return render(request, "store/order_detail.html", {"order": order})


@require_POST
@login_required
def cancel_order(request: HttpRequest, order_number: str) -> HttpResponse:
    """Cancel one of the signed-in customer's orders.

    The lookup is scoped to ``user=request.user``, so guessing another
    customer's order number 404s instead of cancelling their order. Cancelling
    is a POST-only action because it has a real side effect (stock moves back
    to the shelf) and must not fire from a link, a crawler or a prefetch.
    """
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    if order.cancel():
        messages.success(
            request,
            f"Order {order.order_number} was cancelled and its items are back in stock.",
        )
    else:
        messages.error(
            request,
            f"Order {order.order_number} can no longer be cancelled because it has "
            f"{order.get_status_display().lower()}.",
        )
    return redirect("store:order_detail", order_number=order.order_number)


# Static information pages linked from the footer. Keeping them as real routes
# avoids dead placeholder links in the storefront.
INFO_PAGES = {
    "shipping": ("Shipping policy", "store/info_pages.html", "shipping"),
    "returns": ("Returns & refunds", "store/info_pages.html", "returns"),
    "privacy": ("Privacy policy", "store/info_pages.html", "privacy"),
    "terms": ("Terms of service", "store/info_pages.html", "terms"),
}


@require_http_methods(["GET"])
def info_page(request: HttpRequest, page: str) -> HttpResponse:
    entry = INFO_PAGES.get(page)
    if entry is None:
        raise Http404("Unknown information page.")
    title, template, page_key = entry
    return render(
        request,
        template,
        {"page_title": title, "page_key": page_key},
    )


@require_http_methods(["GET", "HEAD"])
def serve_media(request: HttpRequest, path: str) -> HttpResponse:
    """Serve an uploaded file at ``/media/<path>``.

    Uploads live in the database (see ``store.storage.DatabaseStorage``) so they
    survive the ephemeral container filesystems used by Render and similar
    hosts. Files that predate that change - or that were written to disk in
    local development - are still served from ``MEDIA_ROOT`` as a fallback.
    """
    try:
        name = normalize_name(path)
    except SuspiciousFileOperation:
        raise Http404("Invalid media path.")

    # Metadata first, without the blob: an admin page full of thumbnails makes
    # this view the busiest endpoint on the site, and pulling megabytes of
    # image content out of the database just to answer a 304 revalidation (or
    # to compute an ETag) is what used to balloon worker memory.
    record = (
        MediaFile.objects.filter(name=name)
        .only("name", "content_type", "size", "checksum", "updated_at")
        .first()
    )
    if record is None:
        return _serve_media_from_disk(request, name)

    etag = f'"{record.checksum}"' if record.checksum else None
    last_modified = int(record.updated_at.timestamp())
    conditional = get_conditional_response(request, etag=etag, last_modified=last_modified)
    if conditional is not None:
        return conditional

    # Fetch the payload on its own and stream it out in chunks so the response
    # is not assembled as one giant buffer in the worker.
    payload = MediaFile.objects.filter(name=name).values_list("content", flat=True).first()
    if payload is None:  # pragma: no cover - deleted between the two queries
        raise Http404("Media file disappeared while being served.")

    response = StreamingHttpResponse(
        File(BytesIO(payload)),
        content_type=record.content_type or "application/octet-stream",
    )
    response["Content-Length"] = str(len(payload))
    response["Last-Modified"] = http_date(last_modified)
    if etag:
        response["ETag"] = etag
    # Uploads get a fresh, unique name, so they can be cached for a while; the
    # ETag still lets browsers revalidate cheaply once the max-age expires.
    response["Cache-Control"] = f"public, max-age={settings.MEDIA_CACHE_SECONDS}"
    return response


def _serve_media_from_disk(request: HttpRequest, name: str) -> HttpResponse:
    """Fallback for legacy files that were saved to ``MEDIA_ROOT``."""
    try:
        return static_serve(request, name, document_root=settings.MEDIA_ROOT)
    except (SuspiciousFileOperation, ValueError):
        raise Http404("Invalid media path.")


# These handlers are referenced by ecommerce.urls and keep production errors
# friendly when DEBUG=False.
def permission_denied(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "403.html", status=403)


def page_not_found(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "404.html", status=404)


def server_error(request: HttpRequest) -> HttpResponse:
    return render(request, "500.html", status=500)
