"""Shared rate limiter (Stage 9a).

A single :class:`slowapi.Limiter`, keyed by client IP, imported by both
``api_app`` and ``src.auth_api`` so auth/chat/upload routes share one limiter.

In-memory storage — fine for a single backend process (the Docker deployment
runs one uvicorn worker). Horizontal scaling would need a shared backend
(e.g. Redis); that's out of scope for Stage 9a.

Disabled via ``RATE_LIMIT_ENABLED=false`` so the test suite isn't throttled;
the dedicated rate-limit test toggles ``limiter.enabled`` on for its scope.
"""

from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address


def _enabled_from_env() -> bool:
    return os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() != "false"


limiter = Limiter(key_func=get_remote_address, enabled=_enabled_from_env())
