"""Append-only security audit log (Stage 9a).

``record`` writes one :class:`~src.db_models.AuditEvent` per security-relevant
action (login / upload / delete / reindex). It opens its own short-lived
session and **never raises**: a failed audit write must not break the user
action it describes. Routes call it after the action succeeds.
"""

from __future__ import annotations

import logging

from src.db import SessionLocal
from src.db_models import AuditEvent

logger = logging.getLogger("bonchmind.audit")

# Allowed action names — keep the vocabulary small and queryable.
ACTION_LOGIN = "login"
ACTION_UPLOAD = "upload"
ACTION_DELETE = "delete"
ACTION_REINDEX = "reindex"


def record(
    action: str,
    *,
    user_id: str | None = None,
    workspace_id: str | None = None,
    target: str = "",
    ip: str = "",
) -> None:
    """Best-effort write of one audit event. Swallows all errors."""
    try:
        db = SessionLocal()
        try:
            db.add(
                AuditEvent(
                    action=action,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    target=(target or "")[:255],
                    ip=(ip or "")[:64],
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception:  # pragma: no cover - audit must never break the request
        logger.warning("audit write failed for action=%s", action, exc_info=True)
