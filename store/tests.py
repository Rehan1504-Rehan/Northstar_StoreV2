import base64
import os
import tempfile
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.template.defaultfilters import date as date_filter
from django.test import TestCase, override_settings
from django.urls import reverse

from ecommerce.startup import run_startup_tasks

from .admin import ProductAdminForm
from .models import CartItem, Category, MediaFile, Order, OrderItem, Product


User = get_user_model()


class StoreFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="shopper",
            email="shopper@example.com",
            password="Strong-password-123",
            first_name="Shop",
            last_name="Per",
        )
        self.category = Category.objects.create(name="Electronics", description="Useful tech")
        self.product = Product.objects.create(
            name="Desk Light",
            description="A bright and useful desk light.",
            price=Decimal("50.00"),
            discount_price=Decimal("40.00"),
            category=self.category,
            stock_quantity=3,
            available=True,
        )

    def login(self):
        self.assertTrue(self.client.login(username="shopper", password="Strong-password-123"))

    def test_registration_hashes_password_and_persists_user(self):
        response = self.client.post(
            reverse("store:register"),
            {
                "username": "new-customer",
                "email": "new@example.com",
                "first_name": "New",
                "last_name": "Customer",
                "password1": "Another-strong-password-123",
                "password2": "Another-strong-password-123",
            },
        )
        self.assertRedirects(response, reverse("store:login"))
        created = User.objects.get(username="new-customer")
        self.assertNotEqual(created.password, "Another-strong-password-123")
        self.assertTrue(created.check_password("Another-strong-password-123"))

    def test_login_accepts_username_and_email_and_logout(self):
        response = self.client.post(
            reverse("store:login"),
            {"identifier": "shopper@example.com", "password": "Strong-password-123"},
        )
        self.assertRedirects(response, reverse("store:home"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        response = self.client.post(reverse("store:logout"))
        self.assertRedirects(response, reverse("store:home"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_left_navigation_drawer_uses_clean_category_names(self):
        Category.objects.create(name="Gaming", description="Games and consoles")
        Product.objects.create(
            name="Arcade Pad",
            description="A wired game controller.",
            price=Decimal("20.00"),
            category=Category.objects.get(name="Gaming"),
            stock_quantity=2,
            available=True,
        )
        response = self.client.get(reverse("store:home"))
        self.assertContains(response, 'id="navDrawer"')
        self.assertContains(response, "nav-drawer")
        self.assertContains(response, "data-nav-open")
        self.assertContains(response, "Electronics")
        self.assertContains(response, "Gaming")
        self.assertNotContains(response, "Electronics1")
        self.assertNotContains(response, "Gaming1")
        self.assertContains(response, reverse("store:product_list"))
        self.assertContains(response, reverse("store:deals"))
        self.assertContains(response, reverse("store:cart"))
        self.assertContains(response, reverse("store:login"))

    def test_home_and_nav_include_a_section_for_every_stocked_category(self):
        """All Products, Electronics and Gaming are not special-cased.

        Every category that has in-stock products gets the same homepage
        shelf, desktop nav pill and footer link.
        """
        gaming = Category.objects.create(name="Gaming", description="Games and consoles")
        fashion = Category.objects.create(name="Fashion", description="Everyday wear")
        Category.objects.create(name="Empty Aisle", description="Nothing here yet")
        Product.objects.create(
            name="Arcade Pad",
            description="A wired game controller.",
            price=Decimal("20.00"),
            category=gaming,
            stock_quantity=2,
            available=True,
        )
        Product.objects.create(
            name="Canvas Tee",
            description="A soft cotton t-shirt.",
            price=Decimal("18.00"),
            category=fashion,
            stock_quantity=4,
            available=True,
        )
        response = self.client.get(reverse("store:home"))
        self.assertContains(response, 'id="category-electronics"')
        self.assertContains(response, 'id="category-gaming"')
        self.assertContains(response, 'id="category-fashion"')
        self.assertContains(response, "Desk Light")
        self.assertContains(response, "Arcade Pad")
        self.assertContains(response, "Canvas Tee")
        self.assertContains(response, "View all Electronics")
        self.assertContains(response, "View all Gaming")
        self.assertContains(response, "View all Fashion")
        self.assertContains(response, self.category.get_absolute_url())
        self.assertContains(response, gaming.get_absolute_url())
        self.assertContains(response, fashion.get_absolute_url())
        self.assertNotContains(response, "Empty Aisle")
        self.assertContains(response, "header-nav")
        self.assertContains(response, "All Products")

    def test_search_and_category_filter(self):
        other = Product.objects.create(
            name="Canvas Shoes",
            description="Comfortable everyday wear.",
            price=Decimal("65.00"),
            stock_quantity=4,
            available=True,
        )
        response = self.client.get(reverse("store:product_list"), {"q": "desk"})
        self.assertContains(response, "Desk Light")
        self.assertNotContains(response, "Canvas Shoes")
        response = self.client.get(self.category.get_absolute_url())
        self.assertContains(response, "Desk Light")
        self.assertNotContains(response, other.name)

    def test_cart_checkout_reduces_stock_and_keeps_historical_price(self):
        self.login()
        response = self.client.post(
            reverse("store:add_to_cart", args=[self.product.pk]), {"quantity": 2}
        )
        self.assertRedirects(response, reverse("store:cart"))
        self.assertEqual(CartItem.objects.get(product=self.product).quantity, 2)

        response = self.client.post(
            reverse("store:checkout"),
            {"shipping_address": "123 Main Street, Example City 12345", "phone_number": "+1 555 123 4567"},
        )
        order = Order.objects.get(user=self.user)
        self.assertRedirects(response, order.get_absolute_url())
        self.assertEqual(order.total_amount, Decimal("80.00"))
        self.assertEqual(Product.objects.get(pk=self.product.pk).stock_quantity, 1)
        self.assertFalse(CartItem.objects.filter(cart__user=self.user).exists())

        line = order.items.get()
        self.product.price = Decimal("99.00")
        self.product.discount_price = None
        self.product.save()
        line.refresh_from_db()
        self.assertEqual(line.price, Decimal("40.00"))
        self.assertEqual(line.price_at_purchase, Decimal("40.00"))

    def test_cart_rejects_quantity_above_stock(self):
        self.login()
        response = self.client.post(
            reverse("store:add_to_cart", args=[self.product.pk]), {"quantity": 4}
        )
        self.assertRedirects(response, self.product.get_absolute_url())
        self.assertFalse(CartItem.objects.filter(product=self.product).exists())

    def test_order_history_is_private(self):
        self.login()
        order = Order.objects.create(
            user=self.user,
            total_amount=Decimal("1.00"),
            shipping_address="123 Main Street",
            phone_number="5555555",
        )
        other_user = User.objects.create_user(username="other", password="Other-pass-123")
        self.client.force_login(other_user)
        response = self.client.get(order.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_media_served_with_debug_false(self):
        media_file = settings.MEDIA_ROOT / "test_image.png"
        settings.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
        media_file.write_bytes(b"dummy-image-data")
        try:
            with override_settings(DEBUG=False, SERVE_MEDIA=True):
                response = self.client.get("/media/test_image.png")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b"".join(response.streaming_content), b"dummy-image-data")
        finally:
            if media_file.exists():
                media_file.unlink()


class OrderCancellationTests(TestCase):
    """Cancelling calls an order off and hands the units back to the shelf."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="canceller",
            email="canceller@example.com",
            password="Strong-password-123",
        )
        self.category = Category.objects.create(name="Stationery", description="Paper goods")
        self.product = Product.objects.create(
            name="Notebook",
            description="A hard-backed ruled notebook.",
            price=Decimal("20.00"),
            category=self.category,
            stock_quantity=5,
            available=True,
        )

    def place_order(self, quantity=1):
        """Check out for real so the order is built the way customers build it."""
        self.client.force_login(self.user)
        self.client.post(reverse("store:add_to_cart", args=[self.product.pk]), {"quantity": quantity})
        self.client.post(
            reverse("store:checkout"),
            {"shipping_address": "4 Hill Road, Surat 395001", "phone_number": "+91 98765 43210"},
        )
        return Order.objects.get(user=self.user)

    def stock(self):
        return Product.objects.get(pk=self.product.pk).stock_quantity

    def test_customer_can_cancel_a_pending_order_and_stock_returns(self):
        order = self.place_order(quantity=2)
        self.assertEqual(self.stock(), 3, "checkout should have taken the units")

        response = self.client.post(reverse("store:order_cancel", args=[order.order_number]))
        self.assertRedirects(response, order.get_absolute_url())

        order.refresh_from_db()
        self.assertTrue(order.is_cancelled)
        self.assertFalse(order.can_cancel)
        self.assertIsNotNone(order.cancelled_at)
        self.assertEqual(self.stock(), 5, "cancelling should give the units back")

    def test_cancelled_order_page_shows_when_it_was_cancelled(self):
        order = self.place_order(quantity=1)
        self.client.post(reverse("store:order_cancel", args=[order.order_number]))
        order.refresh_from_db()

        page = self.client.get(order.get_absolute_url())

        self.assertContains(page, "This order was cancelled")
        self.assertContains(page, date_filter(order.cancelled_at, "M j, Y · g:i A"))
        # A mistyped template tag would reach the browser as literal "{{ ... }}"
        # text instead of the rendered date, so nothing of the kind may ship.
        self.assertNotContains(page, "{{")

    def test_cancelling_a_sold_out_order_puts_it_back_on_the_shelf(self):
        # Checkout hides a product once it sells out; cancelling has to undo
        # that or the returned unit would be invisible to shoppers.
        self.product.stock_quantity = 1
        self.product.save()
        order = self.place_order(quantity=1)

        product = Product.objects.get(pk=self.product.pk)
        self.assertEqual(product.stock_quantity, 0)
        self.assertFalse(product.available)

        self.client.post(reverse("store:order_cancel", args=[order.order_number]))

        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 1)
        self.assertTrue(product.available)

    def test_cancelling_does_not_re_enable_a_discontinued_product(self):
        # A product switched off by hand while it still had stock is an admin
        # decision, not a sold-out flag, so cancelling must leave it off.
        self.product.available = False
        self.product.save()
        order = Order.objects.create(
            user=self.user,
            total_amount=Decimal("20.00"),
            shipping_address="4 Hill Road",
            phone_number="555",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            quantity=1,
            price=Decimal("20.00"),
        )

        self.client.force_login(self.user)
        self.client.post(reverse("store:order_cancel", args=[order.order_number]))

        product = Product.objects.get(pk=self.product.pk)
        self.assertEqual(product.stock_quantity, 6)
        self.assertFalse(product.available)

    def test_shipped_order_cannot_be_cancelled(self):
        order = self.place_order(quantity=1)
        order.status = Order.Status.SHIPPED
        order.save()

        self.client.post(reverse("store:order_cancel", args=[order.order_number]))

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertIsNone(order.cancelled_at)
        self.assertEqual(self.stock(), 4, "a refused cancel must not restock")

    def test_delivered_order_cannot_be_cancelled(self):
        order = self.place_order(quantity=1)
        order.status = Order.Status.DELIVERED
        order.save()

        self.client.post(reverse("store:order_cancel", args=[order.order_number]))

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertEqual(self.stock(), 4)

    def test_cancelling_twice_only_returns_the_stock_once(self):
        order = self.place_order(quantity=2)
        self.client.post(reverse("store:order_cancel", args=[order.order_number]))
        self.client.post(reverse("store:order_cancel", args=[order.order_number]))

        self.assertEqual(self.stock(), 5)
        self.assertEqual(Order.objects.get(pk=order.pk).status, Order.Status.CANCELLED)

    def test_cancelling_an_order_for_a_deleted_product_is_safe(self):
        order = self.place_order(quantity=1)
        self.product.delete()  # OrderItem.product is SET_NULL, the line stays.

        self.assertTrue(order.cancel())
        self.assertTrue(order.is_cancelled)

    def test_another_customers_order_cannot_be_cancelled(self):
        order = self.place_order(quantity=1)
        other_user = User.objects.create_user(username="other", password="Other-pass-123")
        self.client.force_login(other_user)

        response = self.client.post(reverse("store:order_cancel", args=[order.order_number]))

        self.assertEqual(response.status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(self.stock(), 4)

    def test_cancel_requires_a_post_request(self):
        order = self.place_order(quantity=1)

        response = self.client.get(reverse("store:order_cancel", args=[order.order_number]))

        self.assertEqual(response.status_code, 405)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_cancel_requires_authentication(self):
        order = self.place_order(quantity=1)
        self.client.logout()

        response = self.client.post(reverse("store:order_cancel", args=[order.order_number]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_cancel_button_only_appears_while_the_order_is_cancellable(self):
        order = self.place_order(quantity=1)
        detail_url = reverse("store:order_detail", args=[order.order_number])

        page = self.client.get(detail_url)
        self.assertContains(page, "Cancel this order")
        self.assertContains(page, f"cancel-modal-{order.order_number}")

        order.status = Order.Status.DELIVERED
        order.save()
        page = self.client.get(detail_url)
        self.assertNotContains(page, "Cancel this order")
        self.assertContains(page, "returns policy", html=False)

    def test_order_list_offers_cancel_only_for_live_orders(self):
        cancellable = self.place_order(quantity=1)
        too_late = Order.objects.create(
            user=self.user,
            total_amount=Decimal("5.00"),
            shipping_address="4 Hill Road",
            phone_number="555",
            status=Order.Status.SHIPPED,
        )

        page = self.client.get(reverse("store:order_list"))

        self.assertContains(page, f"cancel-modal-{cancellable.order_number}")
        self.assertNotContains(page, f"cancel-modal-{too_late.order_number}")

    def test_admin_cancel_action_restocks_the_selected_orders(self):
        admin_user = User.objects.create_superuser(
            username="boss", password="Admin-pass-123", email="boss@example.com"
        )
        order = self.place_order(quantity=2)
        self.client.force_login(admin_user)

        response = self.client.post(
            reverse("admin:store_order_changelist"),
            {"action": "cancel_orders", "_selected_action": [str(order.pk)]},
            follow=True,
        )

        order.refresh_from_db()
        self.assertTrue(order.is_cancelled)
        self.assertIsNotNone(order.cancelled_at)
        self.assertEqual(self.stock(), 5)
        self.assertContains(response, "Cancelled 1 order")

    def test_admin_cancel_action_skips_orders_that_are_too_far_along(self):
        admin_user = User.objects.create_superuser(
            username="boss", password="Admin-pass-123", email="boss@example.com"
        )
        order = self.place_order(quantity=1)
        order.status = Order.Status.SHIPPED
        order.save()
        self.client.force_login(admin_user)

        response = self.client.post(
            reverse("admin:store_order_changelist"),
            {"action": "cancel_orders", "_selected_action": [str(order.pk)]},
            follow=True,
        )

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertEqual(self.stock(), 4)
        self.assertContains(response, "Left 1 order")

    def test_cancel_confirmation_modal_is_rendered_at_body_level(self):
        """The confirm dialog must never sit inside a transformed wrapper.

        A Bootstrap modal is ``position: fixed``, and a fixed element is
        positioned against its nearest ancestor that carries a CSS transform
        or ``will-change: transform``. The order cards live inside a
        ``[data-reveal]`` wrapper that has both (and hovering a card lifts it
        with a transform of its own), so a dialog rendered inside the card
        would be re-anchored to that box instead of the viewport: the page
        darkens behind the backdrop while the dialog floats off-centre and the
        buttons underneath stay unclickable. The modals block in base.html
        keeps the dialog a direct child of ``<body>``.
        """
        order = self.place_order(quantity=1)

        class CancelModalScanner(HTMLParser):
            """Collects where each cancel modal and its trigger button sit."""

            def __init__(self):
                super().__init__()
                self.stack = []
                self.modal_parents = {}  # modal element id -> parent tag
                self.trigger_targets = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                classes = attrs.get("class", "").split()
                if tag == "div" and "modal" in classes and attrs.get("id", "").startswith("cancel-modal-"):
                    self.modal_parents[attrs["id"]] = self.stack[-1] if self.stack else None
                if tag == "button" and attrs.get("data-bs-toggle") == "modal":
                    self.trigger_targets.append(attrs.get("data-bs-target", ""))
                self.stack.append(tag)

            def handle_endtag(self, tag):
                for index in range(len(self.stack) - 1, -1, -1):
                    if self.stack[index] == tag:
                        del self.stack[index:]
                        break

        for url in (reverse("store:order_list"), order.get_absolute_url()):
            scanner = CancelModalScanner()
            scanner.feed(self.client.get(url).content.decode())
            self.assertTrue(scanner.modal_parents, f"{url} should offer the cancellation dialog")
            self.assertTrue(scanner.trigger_targets, f"{url} should have a cancel button")
            self.assertEqual(
                set(scanner.modal_parents.values()),
                {"body"},
                f"{url} nests the cancellation modal inside content that would break "
                "its fixed positioning",
            )
            for target in scanner.trigger_targets:
                self.assertIn(
                    target.lstrip("#"),
                    scanner.modal_parents,
                    f"{url} opens a cancel modal that is not on the page",
                )

    def test_cancelled_order_has_no_cancel_modal_or_button(self):
        """Once cancelled there must be nothing left to cancel on the page."""
        order = self.place_order(quantity=1)
        self.client.post(reverse("store:order_cancel", args=[order.order_number]))

        for url in (reverse("store:order_list"), order.get_absolute_url()):
            page = self.client.get(url).content.decode()
            self.assertNotIn("cancel-modal-", page, f"{url} still offers a cancel dialog")
            self.assertNotIn("Cancel this order", page)
            self.assertNotIn(">Cancel order<", page)


class OrderItemDisplayTests(TestCase):
    """Display helpers must survive the blank row Admin renders as a template."""

    def test_line_total_of_a_saved_item_multiplies_price_and_quantity(self):
        item = OrderItem(price=Decimal("20.00"), quantity=3)
        self.assertEqual(item.line_total, Decimal("60.00"))

    def test_line_total_of_an_unsaved_item_does_not_crash(self):
        # Admin renders an empty inline row to clone when adding another, so
        # this property is evaluated on an instance with no figures at all.
        self.assertEqual(OrderItem().line_total, Decimal("0.00"))


# A tiny but genuine 1x1 PNG, so ImageField validation is exercised for real.
ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    "IQAAAABJRU5ErkJggg=="
)


class MediaPersistenceTests(TestCase):
    """Uploads must outlive the container filesystem.

    Hosts such as Render wipe the filesystem on every deploy, which used to
    leave products pointing at a /media/ URL that answered 404.
    """

    def setUp(self):
        self.product = Product.objects.create(
            name="Desk Lamp",
            description="A warm desk lamp.",
            price=Decimal("40.00"),
            stock_quantity=3,
        )

    def upload(self, filename="lamp.png", payload=ONE_PIXEL_PNG):
        self.product.image = SimpleUploadedFile(filename, payload, content_type="image/png")
        self.product.save()
        self.product.refresh_from_db()
        return self.product.image.name

    def test_upload_is_stored_in_the_database_not_on_disk(self):
        name = self.upload()
        self.assertTrue(MediaFile.objects.filter(name=name).exists())
        self.assertEqual(MediaFile.objects.get(name=name).data, ONE_PIXEL_PNG)
        self.assertFalse((Path(settings.MEDIA_ROOT) / name).exists())

    def test_image_url_serves_the_uploaded_bytes(self):
        self.upload()
        url = self.product.image.url
        self.assertTrue(url.startswith("/media/products/"))
        with override_settings(DEBUG=False, SERVE_MEDIA=True):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), ONE_PIXEL_PNG)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("max-age", response["Cache-Control"])

    def test_image_survives_a_wiped_container_filesystem(self):
        """Simulate a redeploy: the disk is empty, the database is not."""
        self.upload()
        url = self.product.image.url
        with override_settings(DEBUG=False, MEDIA_ROOT=Path(tempfile.mkdtemp())):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), ONE_PIXEL_PNG)

    def test_storefront_renders_the_working_image_url(self):
        self.upload()
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, self.product.image.url)
        image_response = self.client.get(self.product.image.url)
        self.assertEqual(image_response.status_code, 200)

    def test_repeat_upload_of_same_filename_keeps_both_products_working(self):
        first = self.upload()
        other = Product.objects.create(
            name="Floor Lamp",
            description="A tall lamp.",
            price=Decimal("60.00"),
            stock_quantity=2,
            image=SimpleUploadedFile("lamp.png", b"", content_type="image/png"),
        )
        other.image = SimpleUploadedFile("lamp.png", ONE_PIXEL_PNG, content_type="image/png")
        other.save()
        other.refresh_from_db()
        self.assertNotEqual(first, other.image.name)
        self.assertEqual(self.client.get(other.image.url).status_code, 200)

    def test_replacing_an_image_removes_the_previous_file(self):
        original = self.upload()
        replacement = self.upload(filename="lamp-v2.png")
        self.assertNotEqual(original, replacement)
        self.assertFalse(MediaFile.objects.filter(name=original).exists())
        self.assertTrue(MediaFile.objects.filter(name=replacement).exists())

    def test_deleting_a_product_removes_its_file(self):
        name = self.upload()
        self.product.delete()
        self.assertFalse(MediaFile.objects.filter(name=name).exists())

    def test_unknown_media_path_returns_404(self):
        with override_settings(DEBUG=False):
            self.assertEqual(self.client.get("/media/products/nope.png").status_code, 404)

    def test_media_path_traversal_is_rejected(self):
        with override_settings(DEBUG=False):
            response = self.client.get("/media/../ecommerce/settings.py")
        self.assertIn(response.status_code, {404, 400})

    def test_conditional_request_returns_304(self):
        self.upload()
        url = self.product.image.url
        first = self.client.get(url)
        second = self.client.get(url, headers={"if-none-match": first["ETag"]})
        self.assertEqual(second.status_code, 304)

    def test_import_command_moves_disk_files_into_the_database(self):
        media_root = Path(tempfile.mkdtemp())
        legacy = media_root / "products" / "2026" / "09" / "legacy.png"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_bytes(ONE_PIXEL_PNG)
        with override_settings(MEDIA_ROOT=media_root):
            call_command("import_media_to_db", verbosity=0)
        record = MediaFile.objects.get(name="products/2026/09/legacy.png")
        self.assertEqual(record.data, ONE_PIXEL_PNG)
        self.assertEqual(record.content_type, "image/png")

    def test_check_media_clears_references_to_lost_files(self):
        Product.objects.filter(pk=self.product.pk).update(image="products/2026/09/gone.png")
        call_command("check_media", "--clear-missing", verbosity=0)
        self.product.refresh_from_db()
        self.assertFalse(self.product.image)

    def test_oversized_upload_is_rejected_by_the_admin_form(self):
        big = SimpleUploadedFile("big.png", ONE_PIXEL_PNG, content_type="image/png")
        big.size = settings.MAX_IMAGE_UPLOAD_BYTES + 1
        form = ProductAdminForm(
            data={
                "name": "Huge",
                "slug": "huge",
                "description": "Too big",
                "price": "10.00",
                "stock_quantity": "1",
                "available": "on",
            },
            files={"image": big},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)


class StartupTaskTests(TestCase):
    """The web process repairs itself on boot, with no dashboard steps."""

    def test_startup_clears_references_to_files_lost_with_the_old_disk(self):
        product = Product.objects.create(
            name="Smart Plug",
            description="A useful plug.",
            price=Decimal("12.00"),
            stock_quantity=5,
        )
        # Exactly the situation on the live site: the row survived in the
        # database, the file did not survive the redeploy.
        Product.objects.filter(pk=product.pk).update(
            image="products/2026/09/standard_smart_plug.webp"
        )

        run_startup_tasks()

        product.refresh_from_db()
        self.assertFalse(product.image)
        # The storefront now shows the placeholder instead of a broken image.
        response = self.client.get(product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "placeholder-image")

    def test_startup_keeps_images_that_are_present(self):
        product = Product.objects.create(
            name="Desk Lamp",
            description="A warm lamp.",
            price=Decimal("40.00"),
            stock_quantity=2,
            image=SimpleUploadedFile("lamp.png", ONE_PIXEL_PNG, content_type="image/png"),
        )
        run_startup_tasks()
        product.refresh_from_db()
        self.assertTrue(product.image)
        self.assertEqual(self.client.get(product.image.url).status_code, 200)

    def test_startup_is_a_no_op_for_disk_backed_media(self):
        """A slow disk mount must never cause a reference to be discarded."""
        product = Product.objects.create(
            name="Mug",
            description="A mug.",
            price=Decimal("9.00"),
            stock_quantity=1,
        )
        Product.objects.filter(pk=product.pk).update(image="products/2026/09/mug.jpg")
        with override_settings(MEDIA_STORAGE="filesystem"):
            run_startup_tasks()
        product.refresh_from_db()
        self.assertEqual(product.image.name, "products/2026/09/mug.jpg")

    def test_startup_can_be_disabled(self):
        product = Product.objects.create(
            name="Kettle",
            description="A kettle.",
            price=Decimal("30.00"),
            stock_quantity=1,
        )
        Product.objects.filter(pk=product.pk).update(image="products/2026/09/gone.jpg")
        with override_settings(RUN_STARTUP_TASKS=False):
            run_startup_tasks()
        product.refresh_from_db()
        self.assertEqual(product.image.name, "products/2026/09/gone.jpg")

    def test_startup_survives_a_broken_database(self):
        with patch("ecommerce.startup._apply_pending_migrations", side_effect=OSError("boom")):
            run_startup_tasks()  # must not raise: the site still has to boot


class ProfileTests(TestCase):
    """The Profile page is private, dynamic, and editable."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="shopper",
            email="shopper@example.com",
            password="Strong-password-123",
            first_name="Shop",
            last_name="Per",
        )

    def login(self):
        self.assertTrue(self.client.login(username="shopper", password="Strong-password-123"))

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse("store:profile"))
        self.assertRedirects(
            response, f"{reverse('store:login')}?next={reverse('store:profile')}"
        )

    def test_profile_shows_the_logged_in_users_own_details(self):
        self.login()
        response = self.client.get(reverse("store:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "shopper")
        self.assertContains(response, "Shop")
        self.assertContains(response, "Per")
        self.assertContains(response, "shopper@example.com")
        self.assertContains(response, reverse("store:profile_edit"))
        self.assertContains(response, reverse("store:change_password"))
        self.assertContains(response, reverse("store:logout"))
        self.assertNotContains(response, "Admin")

    def test_edit_profile_updates_details_and_returns_to_profile(self):
        self.login()
        response = self.client.post(
            reverse("store:profile_edit"),
            {"first_name": "Shop", "last_name": "Pernick", "email": "new@example.com"},
        )
        self.assertRedirects(response, reverse("store:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Shop")
        self.assertEqual(self.user.last_name, "Pernick")
        self.assertEqual(self.user.email, "new@example.com")

    def test_edit_profile_rejects_an_email_owned_by_someone_else(self):
        User.objects.create_user(username="other", email="other@example.com", password="x")
        self.login()
        response = self.client.post(
            reverse("store:profile_edit"),
            {"first_name": "Shop", "last_name": "Per", "email": "other@example.com"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_change_password_updates_and_keeps_the_session(self):
        self.login()
        response = self.client.post(
            reverse("store:change_password"),
            {
                "old_password": "Strong-password-123",
                "new_password1": "New-strong-password-456",
                "new_password2": "New-strong-password-456",
            },
        )
        self.assertRedirects(response, reverse("store:profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New-strong-password-456"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_drawer_shows_profile_when_signed_in_and_not_when_signed_out(self):
        self.login()
        response = self.client.get(reverse("store:home"))
        self.assertContains(response, reverse("store:profile"))
        self.assertNotContains(response, "Hi,")

        self.client.logout()
        response = self.client.get(reverse("store:home"))
        self.assertNotContains(response, reverse("store:profile"))
        self.assertContains(response, reverse("store:login"))
        self.assertContains(response, reverse("store:register"))


class AdminRoutingTests(TestCase):
    """Keep the plural products link compatible with Django Admin."""

    def test_plural_products_path_opens_the_product_changelist(self):
        admin_user = User.objects.create_superuser(
            username="route-admin",
            password="Admin-pass-123",
            email="route-admin@example.com",
        )
        Product.objects.create(
            name="Admin route product",
            description="A product used to verify the admin link.",
            price=Decimal("10.00"),
            stock_quantity=1,
        )
        self.client.force_login(admin_user)

        response = self.client.get("/admin/store/products", follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][0], "/admin/store/product/")
        self.assertContains(response, "Select product to change")
        self.assertContains(response, "Admin route product")


class AdminSetupCommandTests(TestCase):
    def test_create_admin_uses_environment_and_is_idempotent(self):
        env = {
            "ADMIN_USERNAME": "ADMIN",
            "ADMIN_PASSWORD": "Very-strong-admin-password-123",
            "ADMIN_EMAIL": "admin@example.com",
        }
        with patch.dict(os.environ, env, clear=False):
            call_command("create_admin")
            call_command("create_admin")
        admin = User.objects.get(username="ADMIN")
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.check_password(env["ADMIN_PASSWORD"]))
        self.assertEqual(User.objects.filter(username="ADMIN").count(), 1)


class ShopVerseTemplateTests(TestCase):
    def test_empty_catalog_renders_template_without_demo_content(self):
        response = self.client.get(reverse('store:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'store/css/shopverse.css')
        self.assertContains(response, 'sv-hero')
        self.assertContains(response, 'Your next upgrade')
        self.assertContains(response, 'Categories coming soon')
        self.assertNotContains(response, 'ShopVerse')
        self.assertNotContains(response, 'SAVE20')
        self.assertNotContains(response, 'slider-btn')

    def test_template_uses_live_product_category_and_price(self):
        category = Category.objects.create(name='Audio')
        product = Product.objects.create(
            name='Studio Headphones', description='Reference headphones',
            price=Decimal('2500'), discount_price=Decimal('2000'),
            category=category, available=True, stock_quantity=7,
        )
        response = self.client.get(reverse('store:home'))
        self.assertContains(response, product.get_absolute_url())
        self.assertContains(response, category.get_absolute_url())
        self.assertContains(response, 'Studio Headphones')
        self.assertContains(response, '₹2,000')
        self.assertContains(response, '-20%')
        self.assertContains(response, 'sv-category-card')
        self.client.force_login(User.objects.create_user(username='template-shopper'))
        response = self.client.get(reverse('store:home'))
        self.assertContains(response, reverse('store:add_to_cart', args=[product.id]))
        self.assertContains(response, 'csrfmiddlewaretoken')


class AdminProductChangelistTests(TestCase):
    """Guard against the query-per-row pattern that killed the admin page.

    The changelist used to run a Category lookup and an image-existence check
    for every row: 200+ sequential round trips at the default page size, which
    on a remote database outlived the gunicorn worker timeout and surfaced as
    "Internal Server Error" on /admin/store/product/. Rendering N rows must
    cost the same handful of queries as rendering one.
    """

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="list-admin",
            password="Very-strong-admin-password-123",
            email="list-admin@example.com",
        )
        self.client.force_login(self.admin)
        self.category = Category.objects.create(name="Lighting")

    def make_products(self, count, with_image=True):
        for i in range(count):
            product = Product.objects.create(
                name=f"Lamp {i}",
                description="A warm desk lamp.",
                price=Decimal("40.00"),
                category=self.category,
                stock_quantity=2,
            )
            if with_image:
                product.image = SimpleUploadedFile(
                    f"lamp-{i}.png", ONE_PIXEL_PNG, content_type="image/png"
                )
                product.save()

    def changelist_query_count(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("admin:store_product_changelist"))
        self.assertEqual(response.status_code, 200)
        return response, len(captured.captured_queries)

    def test_query_count_does_not_grow_with_the_number_of_rows(self):
        self.make_products(5)
        self.changelist_query_count()  # warm per-process caches first
        _, small = self.changelist_query_count()
        self.make_products(15)
        _, large = self.changelist_query_count()
        self.assertEqual(
            small,
            large,
            "changelist queries must not scale with row count (N+1 regression)",
        )
        # A generous ceiling: sessions, auth, filters and the list itself.
        self.assertLessEqual(large, 15)

    def test_rows_with_a_stored_image_render_the_thumbnail(self):
        self.make_products(1)
        response, _ = self.changelist_query_count()
        self.assertContains(response, "<img")
        self.assertContains(response, "/media/products/")

    def test_rows_pointing_at_a_lost_file_say_so(self):
        self.make_products(1)
        MediaFile.objects.all().delete()
        response, _ = self.changelist_query_count()
        self.assertContains(response, "Missing file — re-upload")

    def test_category_changelist_counts_products_without_a_query_per_row(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.make_products(8, with_image=False)
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("admin:store_category_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "8")
        self.assertLessEqual(len(captured.captured_queries), 8)
