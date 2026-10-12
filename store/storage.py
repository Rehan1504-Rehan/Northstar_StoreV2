"""Database-backed file storage for user uploads.

Container filesystems on platforms such as Render, Railway, Fly.io and Heroku
are *ephemeral*: anything written next to the code is thrown away on the next
deploy, and free instances are also recycled when they go to sleep. A product
image uploaded through Django Admin was therefore saved successfully, kept its
path in the database, and then vanished from disk - leaving the storefront
rendering an ``<img>`` tag that answered ``404``.

This backend stores the uploaded bytes in the same database as the products, so
an image lives exactly as long as the ``Product`` row that points at it. No
persistent disk, no S3 bucket and no third-party account is required.

It is intended for the modest catalogues this project targets. If the shop ever
grows to thousands of large images, switch ``MEDIA_STORAGE`` to ``filesystem``
with a mounted disk, or plug in ``django-storages`` for object storage; the
rest of the code does not care which backend is active.
"""
from __future__ import annotations

import hashlib
import mimetypes
import posixpath
from io import BytesIO
from urllib.parse import urljoin

from django.conf import settings
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils._os import safe_join
from django.utils.deconstruct import deconstructible
from django.utils.encoding import filepath_to_uri


DEFAULT_CONTENT_TYPE = "application/octet-stream"


def normalize_name(name: str) -> str:
    """Return a clean, relative, POSIX-style storage key.

    Raises ``SuspiciousFileOperation`` for traversal attempts such as
    ``../../secrets``.
    """
    cleaned = posixpath.normpath(str(name).replace("\\", "/")).lstrip("/")
    safe_join("/", cleaned)
    return cleaned


def guess_content_type(name: str, content=None) -> str:
    """Best-effort MIME type for a stored file."""
    declared = getattr(content, "content_type", "") or ""
    guessed, _ = mimetypes.guess_type(name)
    # Browsers need a correct type to render an image inline, so prefer a
    # confident guess from the file extension over whatever the client sent.
    return guessed or declared or DEFAULT_CONTENT_TYPE


@deconstructible
class DatabaseStorage(Storage):
    """A ``Storage`` implementation that keeps file contents in the database."""

    def __init__(self, base_url: str | None = None):
        self._base_url = base_url

    # ``deconstructible`` + ``__eq__`` keep migrations and field comparisons
    # stable if this storage is ever attached to a field explicitly.
    def __eq__(self, other):
        return isinstance(other, DatabaseStorage) and self._base_url == other._base_url

    def __hash__(self):
        return hash((self.__class__, self._base_url))

    @property
    def base_url(self) -> str:
        if self._base_url is not None:
            return self._base_url
        return settings.MEDIA_URL

    @staticmethod
    def _model():
        # Imported lazily: the model module imports this module for its own
        # helpers, and app registry is not ready at import time anyway.
        from .models import MediaFile

        return MediaFile

    # -- Reading -----------------------------------------------------------
    def _open(self, name, mode="rb"):
        if "w" in mode or "a" in mode or "+" in mode:
            raise ValueError("DatabaseStorage only supports reading files ('rb').")
        record = self._model().objects.filter(name=normalize_name(name)).first()
        if record is None:
            raise FileNotFoundError(f"No stored file named {name!r}.")
        return File(BytesIO(record.data), name=name)

    # -- Writing -----------------------------------------------------------
    def _save(self, name, content):
        name = normalize_name(name)
        payload = self._read_bytes(content)
        self._model().objects.update_or_create(
            name=name,
            defaults={
                "content": payload,
                "content_type": guess_content_type(name, content),
                "size": len(payload),
                "checksum": hashlib.sha256(payload).hexdigest(),
            },
        )
        return name

    @staticmethod
    def _read_bytes(content) -> bytes:
        """Collect an uploaded file into memory, rewinding it first."""
        if hasattr(content, "seek"):
            try:
                content.seek(0)
            except (OSError, ValueError):
                pass
        if hasattr(content, "chunks"):
            return b"".join(bytes(chunk) for chunk in content.chunks())
        return bytes(content.read())

    def delete(self, name):
        self._model().objects.filter(name=normalize_name(name)).delete()

    # -- Introspection -----------------------------------------------------
    def exists(self, name):
        return self._model().objects.filter(name=normalize_name(name)).exists()

    def size(self, name):
        record = self._record(name, ("size",))
        return record.size

    def url(self, name):
        if name is None:
            raise ValueError("This file has no name and cannot get a URL.")
        return urljoin(self.base_url, filepath_to_uri(normalize_name(name)))

    def get_accessed_time(self, name):
        return self.get_modified_time(name)

    def get_created_time(self, name):
        return self._record(name, ("created_at",)).created_at

    def get_modified_time(self, name):
        return self._record(name, ("updated_at",)).updated_at

    def listdir(self, path):
        path = normalize_name(path) if path not in ("", ".", "/") else ""
        prefix = f"{path}/" if path else ""
        directories, files = set(), []
        names = self._model().objects.filter(name__startswith=prefix).values_list("name", flat=True)
        for name in names:
            remainder = name[len(prefix):]
            head, _, tail = remainder.partition("/")
            if tail:
                directories.add(head)
            else:
                files.append(head)
        return sorted(directories), sorted(files)

    def _record(self, name, fields):
        record = (
            self._model().objects.filter(name=normalize_name(name)).only(*fields).first()
        )
        if record is None:
            raise FileNotFoundError(f"No stored file named {name!r}.")
        return record
