"""SHA-256 helpers for source files and manifests."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def sha256_bytes(content: bytes) -> str:
    """Return the lowercase SHA-256 digest for bytes."""

    return hashlib.sha256(content).hexdigest()


def sha256_text(content: str, *, encoding: str = "utf-8") -> str:
    """Return the SHA-256 digest for encoded text."""

    return sha256_bytes(content.encode(encoding))


def sha256_file(path: Path) -> str:
    """Stream a file into SHA-256 without loading it entirely into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()
