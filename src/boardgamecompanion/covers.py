from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ALLOWED_HOST_SUFFIXES = ("geekdo-images.com", "boardgamegeek.com")
MAX_COVER_BYTES = 10 * 1024 * 1024
CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


class CoverStore:
    """Cache locale delle cover su una cartella montata (mai creata al volo)."""

    def __init__(self, directory: Path, timeout: float = 15.0):
        self.directory = Path(directory)
        self.timeout = timeout

    def available(self) -> bool:
        return self.directory.is_dir() and os.access(self.directory, os.W_OK)

    @staticmethod
    def url_allowed(url: str) -> bool:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        return parts.scheme == "https" and any(
            host == suffix or host.endswith("." + suffix)
            for suffix in ALLOWED_HOST_SUFFIXES
        )

    def _base(self, bgg_id: int, url: str) -> Path:
        digest = hashlib.sha256(url.encode()).hexdigest()[:12]
        return self.directory / f"{int(bgg_id)}-{digest}"

    def find(self, bgg_id: int, url: str) -> Path | None:
        base = self._base(bgg_id, url)
        for ext in CONTENT_TYPES.values():
            path = base.with_suffix(ext)
            if path.is_file():
                return path
        return None

    def fetch(self, bgg_id: int, url: str) -> Path | None:
        """Scarica la cover se manca; None se non disponibile o non fidata."""
        if not self.available() or not self.url_allowed(url):
            return None
        existing = self.find(bgg_id, url)
        if existing:
            return existing
        try:
            with httpx.stream(
                "GET", url, timeout=self.timeout, follow_redirects=False
            ) as response:
                if response.status_code != 200:
                    return None
                kind = response.headers.get("content-type", "").split(";")[0].strip()
                ext = CONTENT_TYPES.get(kind.lower())
                if ext is None:
                    return None
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_COVER_BYTES:
                        return None
        except httpx.HTTPError:
            return None
        target = self._base(bgg_id, url).with_suffix(ext)
        fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, target)
        except OSError:
            Path(tmp).unlink(missing_ok=True)
            return None
        return target
