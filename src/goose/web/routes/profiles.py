"""Profile and feature-gate routes.

v11 Strategy Sprint — expose the ``ProfileConfig`` registry and the current
``FeatureGate`` state to the GUI. Both endpoints are read-only and have no
side effects.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from goose.features import FeatureGate
from goose.forensics.profiles import PROFILE_CONFIGS, get_profile

logger = logging.getLogger(__name__)

# These endpoints live at the app level (not nested under /api/cases).
router = APIRouter(tags=["profiles"])


@router.get("/api/profiles")
async def list_profiles() -> JSONResponse:
    """Return all registered profile configs as a dict keyed by profile_id."""
    return JSONResponse(
        {
            "ok": True,
            "profiles": {pid: cfg.to_dict() for pid, cfg in PROFILE_CONFIGS.items()},
            "count": len(PROFILE_CONFIGS),
        }
    )


@router.get("/api/profiles/{profile_id}")
async def get_profile_route(profile_id: str) -> JSONResponse:
    """Return a single profile config.

    Unknown profile_ids resolve to the default profile rather than 404.
    """
    if profile_id not in PROFILE_CONFIGS:
        # Still return default so the GUI can't crash on a stale id.
        cfg = get_profile(profile_id)
        return JSONResponse(
            {
                "ok": True,
                "profile": cfg.to_dict(),
                "fallback": True,
                "message": f"Unknown profile '{profile_id}', returning default.",
            }
        )
    return JSONResponse(
        {
            "ok": True,
            "profile": PROFILE_CONFIGS[profile_id].to_dict(),
            "fallback": False,
        }
    )


@router.get("/api/features")
async def get_features() -> JSONResponse:
    """Return the current feature-gate / entitlement state."""
    return JSONResponse({"ok": True, **FeatureGate.to_dict()})
