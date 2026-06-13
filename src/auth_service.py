"""Service layer for registration, authentication and the current-user dependency.

Routing (``api_app``) imports from here; tests can import directly to bypass
HTTP. Errors are raised as :class:`fastapi.HTTPException` so both layers see
the same shape.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

import config
from src.auth_models import UserCreate
from src.db import SessionLocal, get_db
from src.db_models import User, Workspace, WorkspaceMember
from src.security import create_access_token, hash_password, verify_password


# ---------------------------------------------------------------------------
# Registration / login primitives
# ---------------------------------------------------------------------------


def _normalize_email(email: str) -> str:
    return email.strip().lower()


# Precomputed bcrypt hash used to equalise login timing: when the email is
# unknown we still run one ``verify_password`` against this dummy hash, so the
# response time doesn't reveal whether an account exists (user enumeration).
_DUMMY_PASSWORD_HASH = hash_password("bonchmind-timing-equalizer")


def register_user(db: Session, payload: UserCreate) -> User:
    """Create a user + their personal workspace atomically.

    Raises ``HTTPException(409)`` if the email is already registered.
    """
    email = _normalize_email(payload.email)
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email_already_registered",
        )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name or email.split("@", 1)[0],
    )
    db.add(user)
    db.flush()  # populate user.id before we reference it below

    _create_personal_workspace(db, user)

    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    """Return the user matching the credentials, or raise 401.

    Always runs exactly one ``verify_password`` — against the real hash if the
    email exists, otherwise against ``_DUMMY_PASSWORD_HASH`` — so the timing of
    "wrong password" and "no such email" is indistinguishable.
    """
    user = db.execute(
        select(User).where(User.email == _normalize_email(email))
    ).scalar_one_or_none()
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(password, password_hash)
    if user is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_credentials",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user_inactive",
        )
    return user


def _create_personal_workspace(db: Session, user: User) -> Workspace:
    """Create the user's personal workspace + owner membership."""
    base_name = (user.display_name or user.email.split("@", 1)[0]).strip() or "My"
    workspace = Workspace(
        name=f"{base_name}'s workspace",
        owner_user_id=user.id,
        plan="free",
    )
    db.add(workspace)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
        )
    )
    return workspace


def get_personal_workspace(db: Session, user: User) -> Workspace:
    """Return the user's personal workspace.

    Stage 1 invariant: exactly one workspace per user, the one created at
    registration. We pick the oldest workspace owned by the user — robust
    against future schema changes that allow multiple workspaces per user.
    """
    workspace = db.execute(
        select(Workspace)
        .where(Workspace.owner_user_id == user.id)
        .order_by(Workspace.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    if workspace is None:
        # Self-heal: a registered user without a workspace is a data-integrity
        # bug, but recreating it costs nothing and avoids a hard 500.
        workspace = _create_personal_workspace(db, user)
        db.commit()
        db.refresh(workspace)
    return workspace


# ---------------------------------------------------------------------------
# Cookie / FastAPI dependency
# ---------------------------------------------------------------------------


def set_auth_cookie(response: Response, token: str) -> None:
    """Attach the JWT to the response as an HttpOnly, SameSite=Lax cookie."""
    response.set_cookie(
        key=config.AUTH_COOKIE_NAME,
        value=token,
        max_age=config.JWT_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=config.AUTH_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=config.AUTH_COOKIE_NAME,
        path="/",
    )


def _resolve_token(
    cookie_token: str | None,
    authorization: str | None,
) -> str | None:
    """Prefer the cookie; fall back to ``Authorization: Bearer <token>``."""
    if cookie_token:
        return cookie_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip() or None
    return None


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    cookie_token: Annotated[str | None, Cookie(alias=config.AUTH_COOKIE_NAME)] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> User:
    """FastAPI dependency that resolves the current user from a JWT.

    Accepts the token from either the HttpOnly cookie set by
    :func:`set_auth_cookie` (preferred for browsers) or an
    ``Authorization: Bearer <token>`` header (handy for scripts/tests).
    """
    from src.security import decode_access_token  # local import to keep cycles obvious

    token = _resolve_token(cookie_token, authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not_authenticated",
        )

    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token",
        )

    user = db.get(User, payload["sub"])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user_not_found",
        )
    if not user.is_active:
        # Banned / deactivated: reject the *live* token too, not just at login,
        # so a ban takes effect immediately on already-issued cookies/JWTs.
        # Kept at 401 (not 403) so the frontend bounces to /login rather than
        # showing a dead-end; the detail stays coarse on purpose.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user_inactive",
        )
    return user


def require_superuser(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """FastAPI dependency that allows only superusers through.

    Used by admin-only endpoints (e.g. ``/api/diagnostics/*``). Regular users
    that pass authentication get a 403, which is more informative than 401
    and signals that the request was understood but the role is wrong.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="superuser_required",
        )
    return current_user


# ---------------------------------------------------------------------------
# Convenience helpers for non-FastAPI callers (tests, scripts)
# ---------------------------------------------------------------------------


def open_session() -> Session:
    """Create a standalone session — caller owns commit/close.

    Useful for one-off scripts and tests that don't go through FastAPI DI.
    """
    return SessionLocal()


def issue_access_token(user: User) -> str:
    return create_access_token(subject=user.id)
