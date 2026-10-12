"""URL configuration for the ecommerce project."""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from store import views as store_views


# Django uses the singular model name in admin URLs (``product``), but the
# storefront and the deployment documentation have historically linked to the
# more natural plural form (``products``). Keep that public link working by
# redirecting it to Django's real changelist URL instead of leaving admins with
# a confusing 404/500-looking error page.
urlpatterns = [
    path(
        "admin/store/products/",
        RedirectView.as_view(
            pattern_name="admin:store_product_changelist",
            permanent=False,
        ),
    ),
    path("admin/", admin.site.urls),
    path("", include("store.urls")),
]

if settings.SERVE_MEDIA:
    # Uploads are served by the same view in development and in production so
    # that a working local image cannot turn into a 404 after deployment. The
    # view reads from the database (MEDIA_STORAGE=database) and falls back to
    # MEDIA_ROOT for files written before that, or by a mounted disk.
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", store_views.serve_media, name="media"),
    ]

handler403 = "store.views.permission_denied"
handler404 = "store.views.page_not_found"
handler500 = "store.views.server_error"
