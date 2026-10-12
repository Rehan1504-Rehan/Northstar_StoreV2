from django.db import DatabaseError
from django.db.models import Count, Q, Sum

from .models import Cart, Category, Product


def cart_context(request):
    """Expose a small cart badge count to every page for signed-in users."""
    cart_count = 0
    if request.user.is_authenticated:
        try:
            cart_count = (
                Cart.objects.filter(user=request.user)
                .aggregate(total=Sum("items__quantity"))
                .get("total")
                or 0
            )
        except DatabaseError:
            # Do not turn a friendly 500/maintenance page into another error
            # when the database is temporarily unavailable.
            cart_count = 0
    return {"cart_count": cart_count}


def storefront_context(request):
    """Categories and deal availability for the header, footer and sidebars.

    Both values are cheap display lookups; if the database is briefly down the
    page still renders with empty navigation instead of raising a second error.
    """
    nav_categories = []
    deals_available = False
    try:
        nav_categories = list(
            Category.objects.annotate(
                product_count=Count(
                    "products",
                    filter=Q(products__available=True, products__stock_quantity__gt=0),
                )
            ).filter(product_count__gt=0)
        )
        deals_available = Product.objects.filter(
            available=True,
            stock_quantity__gt=0,
            discount_price__isnull=False,
        ).exists()
    except DatabaseError:
        nav_categories, deals_available = [], False
    return {
        "nav_categories": nav_categories,
        "deals_available": deals_available,
    }
