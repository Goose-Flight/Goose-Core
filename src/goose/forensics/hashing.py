"""Evidence hashing utilities for Goose forensic case system.

SHA-256 is required for all evidence.
SHA-512 is computed alongside when overhead is acceptable (local ingest).

Sprint 1 — Case & Evidence Foundation
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1024 * 1024  # 1 MB read chunks


def sha256_file(path: str | Path) -> str:
    """Compute SHA-256 of a file. Returns lowercase hex string."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def sha512_file(path: str | Path) -> str:
    """Compute SHA-512 of a file. Returns lowercase hex string."""
    h = hashlib.sha512()
    with open(path, "rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def hash_file(path: str | Path) -> tuple[str, str]:
    """Compute SHA-256 and SHA-512 in a single read pass.

    Returns (sha256_hex, sha512_hex).
    """
    h256 = hashlib.sha256()
    h512 = hashlib.sha512()
    with open(path, "rb") as f:
        while chunk := f.read(_CHUNK):
            h256.update(chunk)
            h512.update(chunk)
    return h256.hexdigest(), h512.hexdigest()


def verify_sha256(path: str | Path, expected: str) -> bool:
    """Return True if the file's SHA-256 matches expected (case-insensitive)."""
    return sha256_file(path).lower() == expected.lower()
