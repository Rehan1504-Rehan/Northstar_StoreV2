"""Move files from MEDIA_ROOT into database-backed storage.

Run this once after switching MEDIA_STORAGE to "database" so that images which
already exist on disk (a local ``media/`` folder, or a mounted persistent disk)
are copied into the database and keep working.
"""
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from store.models import MediaFile
from store.storage import DatabaseStorage, guess_content_type


class Command(BaseCommand):
    help = "Copy files from MEDIA_ROOT into the database so uploads survive redeploys."

    def add_arguments(self, parser):
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace files that are already stored in the database.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without writing anything.",
        )

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT)
        if not media_root.is_dir():
            self.stdout.write(f"Nothing to do: {media_root} does not exist.")
            return

        storage = DatabaseStorage()
        imported = skipped = 0

        for path in sorted(p for p in media_root.rglob("*") if p.is_file()):
            name = path.relative_to(media_root).as_posix()
            if MediaFile.objects.filter(name=name).exists() and not options["overwrite"]:
                skipped += 1
                continue

            if options["dry_run"]:
                self.stdout.write(f"would import {name} ({path.stat().st_size} bytes)")
                imported += 1
                continue

            payload = path.read_bytes()
            content = ContentFile(payload, name=name)
            content.content_type = guess_content_type(name)
            # _save() writes the exact key, bypassing the "find a free name"
            # step, so database keys match what the products already reference.
            storage._save(name, content)
            imported += 1
            self.stdout.write(f"imported {name} ({len(payload)} bytes)")

        verb = "Would import" if options["dry_run"] else "Imported"
        self.stdout.write(
            self.style.SUCCESS(f"{verb} {imported} file(s); skipped {skipped} already stored.")
        )
