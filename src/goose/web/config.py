"""Goose web server configuration.

All settings are readable from environment variables so operators can
override defaults without touching code.  Import the module-level
``settings`` singleton anywhere in the web layer:

    from goose.web.config import settings
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "File too large")

Environment variables
---------------------
GOOSE_MAX_UPLOAD_MB      Max flight-log upload size in MiB  (default 500)
GOOSE_MAX_ATTACHMENT_MB  Max attachment upload size in MiB  (default 50)
GOOSE_API_TOKEN          Bearer token required on all /api/* routes.
                         If unset, auth is disabled (local dev default).
                         Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"
GOOSE_BIND_HOST          Interface to bind  (default 127.0.0.1)
GOOSE_PORT               Port to listen on  (default 8000)
GOOSE_DEBUG              Set to "1" to enable FastAPI debug mode
"""

from __future__ import annotations

import os


class GooseSettings:
    """Runtime configuration for the Goose web server.

    Constructed once at import time from environment variables.
    Change values at runtime via environment before importing this module,
    or mutate the ``settings`` singleton before the first request (tests).
    """

    # ── File upload limits ────────────────────────────────────────────────
    max_upload_mb: int
    max_attachment_mb: int
    # Allowed log file extensions for evidence uploads
    allowed_log_extensions: frozenset[str]

    # ── Auth ─────────────────────────────────────────────────────────────
    api_token: str | None

    # ── Server ───────────────────────────────────────────────────────────
    bind_host: str
    port: int
    debug: bool

    def __init__(self) -> None:
        self.max_upload_mb = int(os.environ.get("GOOSE_MAX_UPLOAD_MB", "500"))
        self.max_attachment_mb = int(os.environ.get("GOOSE_MAX_ATTACHMENT_MB", "50"))
        self.allowed_log_extensions = frozenset(
            {".ulg", ".bin", ".log", ".tlog", ".csv"}
        )
        self.api_token = os.environ.get("GOOSE_API_TOKEN") or None
        self.bind_host = os.environ.get("GOOSE_BIND_HOST", "127.0.0.1")
        self.port = int(os.environ.get("GOOSE_PORT", "8000"))
        self.debug = os.environ.get("GOOSE_DEBUG", "").strip() == "1"

    # ── Computed helpers ──────────────────────────────────────────────────

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_attachment_bytes(self) -> int:
        return self.max_attachment_mb * 1024 * 1024

    @property
    def auth_enabled(self) -> bool:
        return self.api_token is not None

    # ── Settings as dict (for /api/settings endpoint) ────────────────────

    def as_dict(self) -> dict:
        return {
            "max_upload_mb": self.max_upload_mb,
            "max_attachment_mb": self.max_attachment_mb,
            "allowed_log_extensions": sorted(self.allowed_log_extensions),
            "auth_enabled": self.auth_enabled,
            "bind_host": self.bind_host,
            "port": self.port,
            "debug": self.debug,
        }


# Module-level singleton — import this everywhere
settings = GooseSettings()
