from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import File
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, FloatField, Prefetch, Q, Value
from django.db.models.functions import Coalesce
from django.dispatch import receiver
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import get_conditional_response
from django.utils.dateparse import parse_datetime
from django.utils.http import http_date, url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST
from django.views.static import serve as static_serve

from .forms import CheckoutForm, LoginForm, ProfileForm, RegistrationForm, SmartMatchForm
from .models import Cart, CartItem, Category, MediaFile, Order, OrderItem, Product
from .storage import normalize_name
from .templatetags.store_extras import discount_percent, inr, savings_amount


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


_TECH_CATEGORY_KEYWORDS = (
    "electronic",
    "tech",
    "gadget",
    "audio",
    "sound",
    "headphone",
    "earphone",
    "earbud",
    "speaker",
    "game",
    "gaming",
    "console",
    "mobile",
    "phone",
    "smartphone",
    "laptop",
    "computer",
    "camera",
    "tv",
    "television",
    "monitor",
    "display",
    "keyboard",
    "mouse",
    "tablet",
    "watch",
    "wearable",
)

_TECH_PRODUCT_KEYWORDS = (
    "headphone",
    "earphone",
    "earbud",
    "speaker",
    "audio",
    "soundbar",
    "microphone",
    "gaming",
    "controller",
    "console",
    "gamepad",
    "arcade",
    "keyboard",
    "mouse",
    "monitor",
    "display",
    "laptop",
    "computer",
    "webcam",
    "router",
    "ssd",
    "smartphone",
    "tablet",
    "smartwatch",
    "camera",
    "drone",
    "projector",
    "charger",
    "power bank",
    "usb",
    "bluetooth",
    "wireless",
    "smart plug",
    "desk light",
    "lamp",
)

_NON_TECH_KEYWORDS = (
    "planner",
    "stationery",
    "diary",
    "journal",
    "notebook",
    "pen",
    "pencil",
    "book",
    "novel",
    "paper",
    "fashion",
    "cloth",
    "apparel",
    "t-shirt",
    "shirt",
    "tee",
    "jeans",
    "trouser",
    "dress",
    "kurta",
    "saree",
    "jacket",
    "hoodie",
    "shoe",
    "sneaker",
    "sandal",
    "boot",
    "footwear",
    "beauty",
    "cosmetic",
    "skincare",
    "lipstick",
    "shampoo",
    "lotion",
    "cream",
    "perfume",
    "pillow",
    "cushion",
    "curtain",
    "bedsheet",
    "towel",
    "mug",
    "bottle",
    "grocery",
    "cookware",
)

GUEST_CART_SESSION_KEY = "guest_cart"


def _is_tech_product(product: Product) -> bool:
    """Return True when a product fits the electronics, audio, or gaming hero."""
    product_text = f"{product.name} {product.slug}".lower()
    if any(word in product_text for word in _NON_TECH_KEYWORDS):
        return False
    if product.category_id and product.category:
        category_text = f"{product.category.name} {product.category.slug}".lower()
        if any(word in category_text for word in _NON_TECH_KEYWORDS):
            return False
        if any(word in category_text for word in _TECH_CATEGORY_KEYWORDS):
            return True
    full_text = f"{product_text} {product.description or ''}".lower()
    return any(word in full_text for word in _TECH_PRODUCT_KEYWORDS)


_PREFERRED_HERO_SLUGS = (
    "pulsebuds-2-wireless-earbuds",
    "foldable-led-study-lamp",
    "10000mah-slim-power-bank",
    "soundwave-over-ear-headphones",
    "powervolt-25w-gan-charger",
    "slim-casual-backpack",
    "minimal-chrono-watch",
    "insulated-steel-bottle-750ml",
    "aurora-led-strip-10m",
)


def _select_hero_product(in_stock_products: list[Product]) -> Product | None:
    """Pick an in-stock hero product that fits the everyday-life hero theme.

    Checks a prioritized list of flagship everyday products first (such as
    PulseBuds 2 Wireless Earbuds or Foldable LED Study Lamp), then falls back
    gracefully to any available in-stock product with an image, and finally to
    any available in-stock product so no environment ever depends on a single
    database row.
    """
    if not in_stock_products:
        return None
    by_slug = {p.slug: p for p in in_stock_products}
    for slug in _PREFERRED_HERO_SLUGS:
        candidate = by_slug.get(slug)
        if candidate is not None and bool(candidate.image):
            return candidate
    for slug in _PREFERRED_HERO_SLUGS:
        candidate = by_slug.get(slug)
        if candidate is not None:
            return candidate
    tech_with_image = [
        p for p in in_stock_products if _is_tech_product(p) and bool(p.image)
    ]
    if tech_with_image:
        return tech_with_image[0]
    tech_any = [p for p in in_stock_products if _is_tech_product(p)]
    if tech_any:
        return tech_any[0]
    with_image = [p for p in in_stock_products if bool(p.image)]
    if with_image:
        return with_image[0]
    return in_stock_products[0]


def _build_countdown_context(raw_deadline) -> dict | None:
    """Parse a genuine offer deadline into server-side countdown values.

    Returns ``None`` when no deadline is configured or the value cannot be
    parsed, so templates hide the timer instead of inventing a fake one.
    """
    if not raw_deadline:
        return None
    if isinstance(raw_deadline, datetime):
        parsed = raw_deadline
    elif isinstance(raw_deadline, str):
        cleaned = raw_deadline.strip()
        if not cleaned:
            return None
        try:
            parsed = parse_datetime(cleaned)
        except ValueError:
            parsed = None
        if parsed is None:
            return None
    else:
        return None

    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, datetime_timezone.utc)
    else:
        parsed = parsed.astimezone(datetime_timezone.utc)

    now = timezone.now()
    remaining_seconds = max(0, int((parsed - now).total_seconds()))
    expired = remaining_seconds <= 0

    days, rem = divmod(remaining_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    total_hours = days * 24 + hours

    return {
        "iso": parsed.isoformat().replace("+00:00", "Z"),
        "expired": expired,
        "days": f"{days:02d}",
        "hours": f"{hours:02d}",
        "total_hours": f"{total_hours:02d}",
        "minutes": f"{minutes:02d}",
        "seconds": f"{seconds:02d}",
    }


def home(request: HttpRequest) -> HttpResponse:
    in_stock = Q(products__available=True, products__stock_quantity__gt=0)
    all_in_stock = list(
        Product.objects.filter(available=True, stock_quantity__gt=0).select_related("category")
    )
    hero_product = _select_hero_product(all_in_stock)
    featured_products = list(all_in_stock[:8])
    if hero_product and hero_product not in featured_products:
        featured_products = [hero_product] + featured_products[:7]
    elif hero_product and featured_products and featured_products[0].pk != hero_product.pk:
        featured_products = [hero_product] + [
            p for p in featured_products if p.pk != hero_product.pk
        ]
    hero_is_tech = True if hero_product is None else _is_tech_product(hero_product)

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
    deal_products = list(
        Product.objects.filter(
            available=True, stock_quantity__gt=0, discount_price__isnull=False
        ).select_related("category")[:4]
    )
    max_discount = max((discount_percent(p) for p in deal_products), default=0)
    flash_deal_timer = _build_countdown_context(getattr(settings, "FLASH_DEAL_DEADLINE", ""))
    special_offer_timer = _build_countdown_context(getattr(settings, "SPECIAL_OFFER_DEADLINE", ""))
    return render(
        request,
        "store/home.html",
        {
            "hero_product": hero_product,
            "hero_is_tech": hero_is_tech,
            "featured_products": featured_products,
            "category_cards": category_cards,
            "category_sections": category_sections,
            "deal_products": deal_products,
            "max_discount": max_discount,
            "flash_deal_timer": flash_deal_timer,
            "special_offer_timer": special_offer_timer,
        },
    )


SMART_MATCH_CATEGORY_OPTIONS = (
    {
        "key": "audio",
        "label": "Audio & Music",
        "icon": "bi-headphones",
        "hint": "Headphones, earbuds, speakers & mics",
        "keywords": ("audio", "music", "sound", "headphone", "earphone", "earbud", "speaker"),
    },
    {
        "key": "gaming",
        "label": "Gaming",
        "icon": "bi-controller",
        "hint": "Controllers, gaming mice, keyboards & headsets",
        "keywords": ("gaming", "game", "console", "esport"),
    },
    {
        "key": "computers_work_study",
        "label": "Computers, Work & Study",
        "icon": "bi-laptop",
        "hint": "Laptops, keyboards, USB hubs, planners & office gear",
        "keywords": (
            "computer",
            "laptop",
            "stationery",
            "office",
            "work",
            "study",
            "desk",
            "pc",
            "peripheral",
            "book",
        ),
    },
    {
        "key": "electronics_mobile",
        "label": "Electronics & Mobile Accessories",
        "icon": "bi-phone",
        "hint": "Smartphones, tablets, chargers, power banks & cables",
        "keywords": (
            "electronic",
            "mobile",
            "phone",
            "accessor",
            "gadget",
            "tech",
            "tablet",
            "camera",
            "wearable",
        ),
    },
    {
        "key": "home_kitchen_smart",
        "label": "Home & Kitchen / Smart Home",
        "icon": "bi-house-heart",
        "hint": "Smart lighting, Wi-Fi cameras, cookware & storage",
        "keywords": (
            "home",
            "kitchen",
            "smart-home",
            "smart home",
            "appliance",
            "living",
            "lighting",
            "decor",
            "cookware",
        ),
    },
    {
        "key": "fashion_footwear",
        "label": "Fashion & Footwear",
        "icon": "bi-bag-heart",
        "hint": "Sneakers, sandals, backpacks, watches & apparel",
        "keywords": (
            "fashion",
            "footwear",
            "shoe",
            "sneaker",
            "sandal",
            "apparel",
            "cloth",
            "wear",
            "bag",
        ),
    },
    {
        "key": "all",
        "label": "Explore All Categories",
        "icon": "bi-grid-3x3-gap",
        "hint": "Search across every stocked category in the store",
        "keywords": (),
    },
)

SMART_MATCH_BUDGET_OPTIONS = (
    {
        "key": "under_1000",
        "label": "Under ₹1,000",
        "range_note": "Price < ₹1,000",
        "icon": "bi-coin",
    },
    {
        "key": "1000_3000",
        "label": "₹1,000–₹3,000",
        "range_note": "₹1,000 ≤ Price ≤ ₹3,000",
        "icon": "bi-wallet2",
    },
    {
        "key": "3000_5000",
        "label": "Above ₹3,000–₹5,000",
        "range_note": "₹3,000 < Price ≤ ₹5,000",
        "icon": "bi-cash-stack",
    },
    {
        "key": "above_5000",
        "label": "Above ₹5,000",
        "range_note": "Price > ₹5,000",
        "icon": "bi-gem",
    },
    {
        "key": "any",
        "label": "No budget limit",
        "range_note": "Any price",
        "icon": "bi-infinity",
    },
)

SMART_MATCH_SORT_OPTIONS = (
    {
        "key": "price_asc",
        "label": "Lowest price first",
        "hint": "Best for stretching your budget",
        "icon": "bi-sort-numeric-down",
    },
    {
        "key": "price_desc",
        "label": "Highest price first",
        "hint": "Best for flagship & higher-tier picks",
        "icon": "bi-sort-numeric-up-alt",
    },
    {
        "key": "discount_desc",
        "label": "Biggest discount first",
        "hint": "Best for maximum percentage savings",
        "icon": "bi-percent",
    },
    {
        "key": "newest",
        "label": "Newest first",
        "hint": "Best for latest catalog arrivals",
        "icon": "bi-stars",
    },
)

_SMART_CATEGORY_BY_KEY = {item["key"]: item for item in SMART_MATCH_CATEGORY_OPTIONS}
_SMART_BUDGET_BY_KEY = {item["key"]: item for item in SMART_MATCH_BUDGET_OPTIONS}
_SMART_SORT_BY_KEY = {item["key"]: item for item in SMART_MATCH_SORT_OPTIONS}


def _filter_smart_match_category(queryset, category_key: str):
    """Filter products to the categories mapped to ``category_key``."""
    option = _SMART_CATEGORY_BY_KEY.get(category_key)
    if not option or category_key == "all" or not option["keywords"]:
        return queryset
    cat_q = Q()
    for kw in option["keywords"]:
        cat_q |= Q(category__name__icontains=kw) | Q(category__slug__icontains=kw)
    return queryset.filter(cat_q)


def _filter_smart_match_budget(queryset, budget_key: str):
    """Apply exact, non-overlapping budget boundaries on ``effective_price``."""
    if budget_key == "under_1000":
        return queryset.filter(effective_price__lt=Decimal("1000.00"))
    if budget_key == "1000_3000":
        return queryset.filter(
            effective_price__gte=Decimal("1000.00"),
            effective_price__lte=Decimal("3000.00"),
        )
    if budget_key == "3000_5000":
        return queryset.filter(
            effective_price__gt=Decimal("3000.00"),
            effective_price__lte=Decimal("5000.00"),
        )
    if budget_key == "above_5000":
        return queryset.filter(effective_price__gt=Decimal("5000.00"))
    return queryset


def _sort_smart_match_products(queryset, sort_key: str):
    """Order matching products according to the shopper's chosen preference."""
    if sort_key == "price_asc":
        return queryset.order_by("effective_price", "-created_at", "id")
    if sort_key == "price_desc":
        return queryset.order_by("-effective_price", "-created_at", "id")
    if sort_key == "discount_desc":
        return queryset.order_by(
            "-discount_fraction", "-discount_amount", "effective_price", "-created_at", "id"
        )
    return queryset.order_by("-created_at", "-id")


def _build_smart_match_reason(
    product: Product, category_key: str, budget_key: str, sort_key: str
) -> str:
    """Build an accurate, stored-data-only explanation for why this product matched."""
    category_name = product.category.name if product.category else "Store Catalog"
    cat_label = _SMART_CATEGORY_BY_KEY.get(category_key, {}).get("label", "All Categories")
    if category_key == "all":
        category_part = f"From {category_name}"
    else:
        category_part = f"In {category_name} (matched for {cat_label})"

    selling_price = inr(product.get_price())
    budget_phrases = {
        "under_1000": f"priced at {selling_price} (under ₹1,000)",
        "1000_3000": f"priced at {selling_price} (within ₹1,000–₹3,000)",
        "3000_5000": f"priced at {selling_price} (within Above ₹3,000–₹5,000)",
        "above_5000": f"priced at {selling_price} (above ₹5,000)",
        "any": f"priced at {selling_price}",
    }
    price_part = budget_phrases.get(budget_key, f"priced at {selling_price}")

    if product.has_discount:
        off_pct = discount_percent(product)
        saved = inr(savings_amount(product))
        regular_price = inr(product.price)
        discount_part = f"saves {saved} ({off_pct}% off list price {regular_price})"
    else:
        discount_part = "at its standard list price"

    sort_phrases = {
        "price_asc": "ranked by lowest selling price",
        "price_desc": "ranked by highest selling price",
        "discount_desc": "ranked by biggest discount",
        "newest": "ranked by newest arrival",
    }
    sort_part = sort_phrases.get(sort_key, "ranked by your preference")
    stock_part = f"{product.stock_quantity} in stock"

    return f"{category_part}, {price_part} — {discount_part}, {sort_part} ({stock_part})."


@require_http_methods(["GET", "POST"])
def smart_match(request: HttpRequest) -> HttpResponse:
    """Rule-based Northstar Smart Match product recommendation view."""
    raw_params = request.POST if request.method == "POST" else request.GET
    has_submission = request.method == "POST" or any(
        key in raw_params
        for key in ("category", "interest", "budget", "sort", "sort_by")
    )

    base_stock_qs = (
        _annotated_products()
        .filter(stock_quantity__gt=0)
        .annotate(
            discount_amount=ExpressionWrapper(
                F("price") - Coalesce("discount_price", F("price")),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        )
    )
    catalog_empty = not base_stock_qs.exists()

    default_choices = {
        "category": "all",
        "budget": "any",
        "sort": "discount_desc",
    }

    recommendations = []
    total_matches = 0
    selected_summary = None

    if has_submission:
        form = SmartMatchForm(raw_params)
        if form.is_valid():
            category_key = form.cleaned_data["category"]
            budget_key = form.cleaned_data["budget"]
            sort_key = form.cleaned_data["sort"]
            selected_choices = {
                "category": category_key,
                "budget": budget_key,
                "sort": sort_key,
            }
            selected_summary = {
                "category_label": _SMART_CATEGORY_BY_KEY[category_key]["label"],
                "budget_label": _SMART_BUDGET_BY_KEY[budget_key]["label"],
                "sort_label": _SMART_SORT_BY_KEY[sort_key]["label"],
            }
            if not catalog_empty:
                matched_qs = _filter_smart_match_category(base_stock_qs, category_key)
                matched_qs = _filter_smart_match_budget(matched_qs, budget_key)
                matched_qs = _sort_smart_match_products(matched_qs, sort_key)
                total_matches = matched_qs.count()
                for idx, prod in enumerate(matched_qs[:3], start=1):
                    recommendations.append(
                        {
                            "rank": idx,
                            "product": prod,
                            "reason": _build_smart_match_reason(
                                prod, category_key, budget_key, sort_key
                            ),
                        }
                    )
        else:
            selected_choices = {
                "category": raw_params.get("category") or raw_params.get("interest") or default_choices["category"],
                "budget": raw_params.get("budget") or default_choices["budget"],
                "sort": raw_params.get("sort") or raw_params.get("sort_by") or default_choices["sort"],
            }
    else:
        form = SmartMatchForm(initial=default_choices)
        selected_choices = default_choices

    return render(
        request,
        "store/smart_match.html",
        {
            "form": form,
            "has_submission": has_submission,
            "catalog_empty": catalog_empty,
            "recommendations": recommendations,
            "total_matches": total_matches,
            "selected_choices": selected_choices,
            "selected_summary": selected_summary,
            "category_options": SMART_MATCH_CATEGORY_OPTIONS,
            "budget_options": SMART_MATCH_BUDGET_OPTIONS,
            "sort_options": SMART_MATCH_SORT_OPTIONS,
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
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your account was created. You can now sign in.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(f"{reverse('store:login')}?{urlencode({'next': next_url})}")
        return redirect("store:login")
    return render(request, "store/register.html", {"form": form, "next": next_url})


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("store:home")

    next_url = request.GET.get("next") or request.POST.get("next") or ""
    form = LoginForm(request=request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)
        merge_guest_cart_into_user_cart(request, user)
        if not form.cleaned_data.get("remember_me"):
            # Session-only cookie: signed out when the browser closes.
            request.session.set_expiry(0)
        messages.success(request, f"Welcome back, {user.get_username()}!")
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


class GuestCartItem:
    """In-memory line item for a session-backed guest cart.

    Prices and subtotals are always computed on the server from the live
    ``Product`` model — never stored in the session or read from the client.
    """

    def __init__(self, product: Product, quantity: int):
        self.id = product.pk
        self.pk = product.pk
        self.product = product
        self.product_id = product.pk
        self.quantity = quantity

    @property
    def subtotal(self) -> Decimal:
        return self.product.get_price() * self.quantity


class GuestCart:
    """Lightweight cart wrapper for templates when the shopper is signed out."""

    def __init__(self, items: list[GuestCartItem]):
        self.items = items

    def item_count(self) -> int:
        return sum(item.quantity for item in self.items)

    def total(self) -> Decimal:
        return sum((item.subtotal for item in self.items), Decimal("0.00"))


def _get_session_cart(request: HttpRequest) -> dict[str, int]:
    """Read and sanitize the guest cart mapping ``{product_id_str: quantity}``."""
    session = getattr(request, "session", None)
    if session is None:
        return {}
    raw = session.get(GUEST_CART_SESSION_KEY, {})
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, int] = {}
    for key, value in raw.items():
        try:
            pid = int(str(key).strip())
            qty = int(value)
        except (TypeError, ValueError):
            continue
        if pid > 0 and qty > 0:
            cleaned[str(pid)] = qty
    return cleaned


def _save_session_cart(request: HttpRequest, cart_data: dict[str, int]) -> None:
    """Persist the sanitized guest cart dictionary into the session."""
    session = getattr(request, "session", None)
    if session is None:
        return
    sanitized = {str(k): int(v) for k, v in cart_data.items() if int(v) > 0}
    if sanitized:
        session[GUEST_CART_SESSION_KEY] = sanitized
    else:
        session.pop(GUEST_CART_SESSION_KEY, None)
    session.modified = True


def get_guest_cart_count(request: HttpRequest) -> int:
    """Total item quantity currently in the guest's session cart."""
    return sum(_get_session_cart(request).values())


def _get_guest_cart_and_items(request: HttpRequest) -> tuple[GuestCart, list[GuestCartItem]]:
    """Build guest cart items using trusted product rows from the database."""
    session_cart = _get_session_cart(request)
    if not session_cart:
        return GuestCart([]), []

    product_ids = [int(pid) for pid in session_cart.keys()]
    products_by_id = {
        product.pk: product
        for product in Product.objects.filter(pk__in=product_ids).select_related("category")
    }
    items: list[GuestCartItem] = []
    stale_removed = False
    for pid_str, quantity in list(session_cart.items()):
        product = products_by_id.get(int(pid_str))
        if product is None:
            session_cart.pop(pid_str, None)
            stale_removed = True
            continue
        items.append(GuestCartItem(product=product, quantity=quantity))

    if stale_removed:
        _save_session_cart(request, session_cart)

    return GuestCart(items), items


def merge_guest_cart_into_user_cart(request: HttpRequest | None, user) -> None:
    """Merge any session guest cart into the authenticated user's database cart.

    - Preserves all existing items in the user's account cart.
    - Sums quantities when the same product exists in both carts.
    - Caps quantities at available product stock and notifies the user if any
      line had to be adjusted.
    """
    if request is None or user is None or not getattr(user, "is_authenticated", False):
        return
    session_cart = _get_session_cart(request)
    if not session_cart:
        return

    # Clear the session cart up front so duplicate calls (signal + view) are a no-op.
    _save_session_cart(request, {})

    with transaction.atomic():
        cart, _ = Cart.objects.get_or_create(user=user)
        existing_items = {
            item.product_id: item
            for item in CartItem.objects.select_for_update().filter(cart=cart)
        }
        product_ids = [int(pid) for pid in session_cart.keys()]
        products = {
            product.pk: product
            for product in Product.objects.select_for_update().filter(pk__in=product_ids)
        }

        for pid_str, guest_qty in session_cart.items():
            pid = int(pid_str)
            product = products.get(pid)
            existing_item = existing_items.get(pid)
            if product is None:
                continue

            if not product.available or product.stock_quantity <= 0:
                if existing_item is None:
                    messages.add_message(
                        request,
                        messages.WARNING,
                        f"{product.name} is currently out of stock and could not be added to your cart.",
                        fail_silently=True,
                    )
                continue

            if existing_item is not None:
                desired_qty = existing_item.quantity + guest_qty
                new_qty = min(desired_qty, product.stock_quantity)
                if new_qty < desired_qty:
                    messages.add_message(
                        request,
                        messages.WARNING,
                        f"Only {product.stock_quantity} item(s) of {product.name} are in stock; "
                        f"your cart quantity was set to {new_qty}.",
                        fail_silently=True,
                    )
                if existing_item.quantity != new_qty:
                    existing_item.quantity = new_qty
                    existing_item.save(update_fields=["quantity"])
            else:
                new_qty = min(guest_qty, product.stock_quantity)
                if new_qty < guest_qty:
                    messages.add_message(
                        request,
                        messages.WARNING,
                        f"Only {product.stock_quantity} item(s) of {product.name} are in stock; "
                        f"added {new_qty} to your cart.",
                        fail_silently=True,
                    )
                existing_items[pid] = CartItem.objects.create(
                    cart=cart,
                    product=product,
                    quantity=new_qty,
                )

        cart.save(update_fields=["updated_at"])


@receiver(user_logged_in)
def _merge_guest_cart_on_login(sender, request, user, **kwargs):
    merge_guest_cart_into_user_cart(request, user)


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


def cart_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        cart = _get_user_cart(request)
        items = list(cart.items.select_related("product", "product__category").all())
    else:
        cart, items = _get_guest_cart_and_items(request)
    context = {"cart": cart, "items": items, **_cart_totals(items)}
    return render(request, "store/cart.html", context)


@require_POST
def add_to_cart(request: HttpRequest, product_id: int) -> HttpResponse:
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    product = get_object_or_404(Product, pk=product_id, available=True)

    def add_error(message: str, status: int = 400):
        if wants_json:
            return JsonResponse({"ok": False, "message": message}, status=status)
        messages.error(request, message)
        return redirect(product.get_absolute_url())

    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 0

    if quantity < 1:
        return add_error("Choose a quantity of at least one.")
    if quantity > product.stock_quantity:
        return add_error(f"Only {product.stock_quantity} item(s) are currently in stock.")

    if request.user.is_authenticated:
        cart = _get_user_cart(request)
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={"quantity": quantity},
        )
        if not created:
            new_quantity = item.quantity + quantity
            if new_quantity > product.stock_quantity:
                return add_error(
                    f"Your cart cannot contain more than {product.stock_quantity} of this product."
                )
            item.quantity = new_quantity
            item.save(update_fields=["quantity"])
        cart.save(update_fields=["updated_at"])
        cart_count = cart.item_count()
    else:
        guest_cart = _get_session_cart(request)
        key = str(product.pk)
        existing_quantity = guest_cart.get(key, 0)
        new_quantity = existing_quantity + quantity
        if new_quantity > product.stock_quantity:
            return add_error(
                f"Your cart cannot contain more than {product.stock_quantity} of this product."
            )
        guest_cart[key] = new_quantity
        _save_session_cart(request, guest_cart)
        cart_count = sum(guest_cart.values())

    success_message = f"{product.name} was added to your cart."
    if wants_json:
        return JsonResponse({
            "ok": True,
            "message": success_message,
            "cart_count": cart_count,
        })
    messages.success(request, success_message)
    if request.POST.get("buy_now") == "1":
        return redirect("store:checkout")
    return redirect("store:cart")


@require_POST
def update_cart(request: HttpRequest, item_id: int) -> HttpResponse:
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    # A missing or unreadable quantity is a broken request, not a request to
    # delete the line. Treating it as zero used to wipe cart rows whenever a
    # client posted without the field (for example a submit button that was
    # already disabled, so it never made it into the form data).
    try:
        quantity = int(str(request.POST.get("quantity", "")).strip())
    except (TypeError, ValueError):
        message = "We could not tell which quantity you wanted. Please try again."
        if wants_json:
            return JsonResponse({"ok": False, "message": message}, status=400)
        messages.error(request, message)
        return redirect("store:cart")

    if request.user.is_authenticated:
        item = get_object_or_404(
            CartItem.objects.select_related("product"),
            pk=item_id,
            cart__user=request.user,
        )
        if quantity <= 0:
            item.delete()
            message = f"{item.product.name} was removed from your cart."
            if not wants_json:
                messages.info(request, message)
        elif not item.product.available:
            message = f"{item.product.name} is no longer available."
            if wants_json:
                return JsonResponse({"ok": False, "message": message}, status=400)
            messages.error(request, message)
        elif quantity > item.product.stock_quantity:
            message = f"Only {item.product.stock_quantity} item(s) of {item.product.name} are in stock."
            if wants_json:
                return JsonResponse({"ok": False, "message": message}, status=400)
            messages.error(request, message)
        else:
            item.quantity = quantity
            item.save(update_fields=["quantity"])
            item.cart.save(update_fields=["updated_at"])
            message = "Your cart was updated."
            if not wants_json:
                messages.success(request, message)
        if wants_json:
            return JsonResponse({"ok": True, "message": message, "cart_count": item.cart.item_count()})
        return redirect("store:cart")

    guest_cart = _get_session_cart(request)
    key = str(item_id)
    if key not in guest_cart:
        raise Http404("Item not found in guest cart.")

    product = Product.objects.filter(pk=item_id).first()
    if product is None:
        guest_cart.pop(key, None)
        _save_session_cart(request, guest_cart)
        raise Http404("Product not found.")

    if quantity <= 0:
        guest_cart.pop(key, None)
        _save_session_cart(request, guest_cart)
        message = f"{product.name} was removed from your cart."
        if not wants_json:
            messages.info(request, message)
    elif not product.available:
        message = f"{product.name} is no longer available."
        if wants_json:
            return JsonResponse({"ok": False, "message": message}, status=400)
        messages.error(request, message)
    elif quantity > product.stock_quantity:
        message = f"Only {product.stock_quantity} item(s) of {product.name} are in stock."
        if wants_json:
            return JsonResponse({"ok": False, "message": message}, status=400)
        messages.error(request, message)
    else:
        guest_cart[key] = quantity
        _save_session_cart(request, guest_cart)
        message = "Your cart was updated."
        if not wants_json:
            messages.success(request, message)

    if wants_json:
        return JsonResponse(
            {"ok": True, "message": message, "cart_count": sum(guest_cart.values())}
        )
    return redirect("store:cart")


@require_POST
def remove_from_cart(request: HttpRequest, item_id: int) -> HttpResponse:
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if request.user.is_authenticated:
        item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
        name = item.product.name
        cart = item.cart
        item.delete()
        cart_count = cart.item_count()
    else:
        guest_cart = _get_session_cart(request)
        key = str(item_id)
        if key not in guest_cart:
            raise Http404("Item not found in guest cart.")
        product = Product.objects.filter(pk=item_id).first()
        name = product.name if product else "Item"
        guest_cart.pop(key, None)
        _save_session_cart(request, guest_cart)
        cart_count = sum(guest_cart.values())

    message = f"{name} was removed from your cart."
    if wants_json:
        return JsonResponse({"ok": True, "message": message, "cart_count": cart_count})
    messages.info(request, message)
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
