"""Ephemeral image payloads: graph checkpoints contain opaque refs, never image bytes."""
from __future__ import annotations

import secrets
import threading
import time
from typing import Protocol

from ..tools.service import UploadedImage


class ImageStore(Protocol):
    """A production host may inject an access-controlled, expiring object store."""
    def put(self, image: UploadedImage) -> str: ...
    def get(self, reference: str) -> UploadedImage | None: ...
    def delete(self, reference: str) -> None: ...


class InMemoryImageStore:
    def __init__(self, ttl_seconds: int = 900, max_items: int = 64) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        self._items: dict[str, tuple[float, UploadedImage]] = {}
        self._lock = threading.Lock()

    def _purge(self) -> None:
        now = time.monotonic()
        for ref, (expiry, _) in list(self._items.items()):
            if expiry <= now:
                self._items.pop(ref, None)

    def put(self, image: UploadedImage) -> str:
        with self._lock:
            self._purge()
            if len(self._items) >= self.max_items:
                raise ValueError("image_store_capacity_exceeded")
            reference = secrets.token_urlsafe(24)
            self._items[reference] = (time.monotonic() + self.ttl_seconds, image)
            return reference

    def get(self, reference: str) -> UploadedImage | None:
        with self._lock:
            self._purge()
            item = self._items.get(reference)
            return item[1] if item else None

    def delete(self, reference: str) -> None:
        with self._lock:
            self._items.pop(reference, None)
