"""Runtime feature flags shared across backend entry points."""

from __future__ import annotations

import os

from fastapi import HTTPException, status

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})


def _get_bool_env(name: str, *, default: bool = False) -> bool:
    """Read an explicit boolean environment variable with a safe fallback."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return default


def is_inspirations_enabled() -> bool:
    """Return whether the inspiration-library module is enabled right now."""
    return _get_bool_env("INSPIRATIONS_ENABLED", default=False)


def require_inspirations_enabled() -> None:
    """Hide inspiration routes when the module is disabled."""
    if not is_inspirations_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
