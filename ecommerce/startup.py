"""Tasks that run once when the web server process boots.

The point of this module is that deploying the app should not require anyone to
remember a dashboard setting. Render (and Railway, Fly.io, Heroku) start the
service with the start command only; if the build step forgets
``manage.py migrate``, the database is missing tables the app needs and admins
get errors when saving. Running the migration here makes a plain
``gunicorn ecommerce.wsgi`` deploy correct on its own.

Everything below is idempotent, cheap when there is nothing to do, and never
fatal: a task that fails logs the problem and lets the site come up anyway,
because a running store with one stale row beats a store that will not boot.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import connection, connections


logger = logging.getLogger(__name__)

# Arbitrary constant identifying our PostgreSQL advisory lock, so two workers
# booting at the same time cannot run migrations concurrently.
_MIGRATION_LOCK_KEY = 4_812_003_117


def run_startup_tasks() -> None:
    """Apply pending migrations, then repair references to deleted uploads."""
    if not getattr(settings, "RUN_STARTUP_TASKS", True):
        return
    try:
        _with_lock(_apply_pending_migrations)
        _with_lock(_clear_missing_product_images)
    except Exception:  # pragma: no cover - startup must never crash the site
        logger.exception("Startup tasks failed; continuing to serve requests.")


def _with_lock(task) -> None:
    """Run ``task`` while holding a cross-process lock, where available."""
    if connection.vendor != "postgresql":
        # SQLite deployments are single-process, so no coordination is needed.
        task()
        return

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", [_MIGRATION_LOCK_KEY])
        try:
            task()
        finally:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [_MIGRATION_LOCK_KEY])


def _apply_pending_migrations() -> None:
    from django.core.management import call_command
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connections["default"])
    targets = executor.loader.graph.leaf_nodes()
    # An empty plan is the normal case, and costs one cheap query.
    if not executor.migration_plan(targets):
        return

    logger.info("Applying pending database migrations before serving requests.")
    call_command("migrate", interactive=False, verbosity=1)
    logger.info("Database migrations are up to date.")


def _clear_missing_product_images() -> None:
    """Detach product images whose file no longer exists.

    Images uploaded before media moved into the database were written to the
    container's ephemeral disk and destroyed by the next deploy. The product
    rows still point at them, which renders a broken image on the storefront.
    Blanking those references shows the neutral placeholder instead, and the
    picture can simply be uploaded again.
    """
    if settings.MEDIA_STORAGE != "database":
        # With a mounted disk a file could merely be slow to appear; never
        # discard a reference we cannot be certain about.
        return

    from store.models import MediaFile, Product

    referenced = set(
        Product.objects.exclude(image="").exclude(image__isnull=True).values_list("image", flat=True)
    )
    if not referenced:
        return

    # Chunk the lookup: a big IN (...) with thousands of names is slow to plan
    # and hammers memory on small instances, and this runs at every worker boot.
    stored = set()
    referenced_list = sorted(referenced)
    for start in range(0, len(referenced_list), 500):
        chunk = referenced_list[start : start + 500]
        stored.update(
            MediaFile.objects.filter(name__in=chunk).values_list("name", flat=True)
        )
    missing = referenced - stored
    if not missing:
        return

    updated = Product.objects.filter(image__in=missing).update(image="")
    logger.warning(
        "Cleared %s product image reference(s) whose file was lost with an "
        "earlier ephemeral filesystem: %s. Re-upload the pictures in Django Admin.",
        updated,
        ", ".join(sorted(missing)),
    )
