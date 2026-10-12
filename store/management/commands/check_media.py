"""Report and repair product images whose file is missing from storage.

Uploads made before media moved into the database were written to the
container's ephemeral filesystem and deleted by the next deploy, leaving
products that point at a file which no longer exists. Those rows render a
broken image on the storefront; this command finds them.
"""
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from store.models import MediaFile, Product


class Command(BaseCommand):
    help = "Find product images missing from storage, and optionally clean them up."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear-missing",
            action="store_true",
            help="Blank the image field of products whose file is gone, so the "
            "storefront shows the neutral placeholder instead of a broken image.",
        )
        parser.add_argument(
            "--prune-orphans",
            action="store_true",
            help="Delete stored files that no product references any more.",
        )

    def handle(self, *args, **options):
        missing = []
        for product in Product.objects.exclude(image="").exclude(image__isnull=True):
            if not default_storage.exists(product.image.name):
                missing.append(product)

        if missing:
            self.stdout.write(self.style.WARNING(f"{len(missing)} product(s) with a missing image:"))
            for product in missing:
                self.stdout.write(f"  #{product.pk} {product.name} -> {product.image.name}")
            if options["clear_missing"]:
                for product in missing:
                    Product.objects.filter(pk=product.pk).update(image="")
                self.stdout.write(
                    self.style.SUCCESS(f"Cleared {len(missing)} broken image reference(s).")
                )
            else:
                self.stdout.write("Re-upload them, or run again with --clear-missing.")
        else:
            self.stdout.write(self.style.SUCCESS("Every product image is present in storage."))

        referenced = set(
            Product.objects.exclude(image="")
            .exclude(image__isnull=True)
            .values_list("image", flat=True)
        )
        orphans = MediaFile.objects.exclude(name__in=referenced)
        count = orphans.count()
        if count and options["prune_orphans"]:
            orphans.delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted {count} unreferenced stored file(s)."))
        elif count:
            self.stdout.write(
                f"{count} stored file(s) are not referenced by any product "
                "(run with --prune-orphans to delete them)."
            )
