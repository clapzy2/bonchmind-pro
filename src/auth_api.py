"""FastAPI router for ``/api/auth/*`` endpoints.

Kept in its own module so :mod:`api_app` stays a thin composition root and
the auth surface is easy to test in isolation.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

import config
from src import audit_service, auth_service
from src.auth_models import (
    AuthResponse,
    MessageResponse,
    UserCreate,
    UserLogin,
    UserOut,
    WorkspaceOut,
)
from src.db import get_db
from src.db_models import User
from src.rate_limit import limiter


router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _build_user_out(db: Session, user: User) -> UserOut:
    workspace = auth_service.get_personal_workspace(db, user)
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
        personal_workspace=WorkspaceOut.model_validate(workspace),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(config.RATE_LIMIT_REGISTER, key_func=get_remote_address)
def register(
    payload: UserCreate,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthResponse:
    user = auth_service.register_user(db, payload)
    token = auth_service.issue_access_token(user)
    auth_service.set_auth_cookie(response, token)
    return AuthResponse(access_token=token, user=_build_user_out(db, user))


@router.post("/login", response_model=AuthResponse)
@limiter.limit(config.RATE_LIMIT_LOGIN, key_func=get_remote_address)
def login(
    payload: UserLogin,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthResponse:
    user = auth_service.authenticate_user(db, payload.email, payload.password)
    token = auth_service.issue_access_token(user)
    auth_service.set_auth_cookie(response, token)
    audit_service.record(
        audit_service.ACTION_LOGIN,
        user_id=user.id,
        ip=_client_ip(request),
    )
    return AuthResponse(access_token=token, user=_build_user_out(db, user))


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    current_user: Annotated[User, Depends(auth_service.get_current_user)],
) -> MessageResponse:
    """Clear the auth cookie. Requires a valid session to prevent CSRF-style
    cookie-clearing attacks on anonymous visitors and to give a clear
    semantic: "this caller had a session and now does not"."""
    del current_user  # only used for the auth gate
    auth_service.clear_auth_cookie(response)
    return MessageResponse(message="logged_out")


@router.get("/me", response_model=UserOut)
def me(
    current_user: Annotated[User, Depends(auth_service.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> UserOut:
    return _build_user_out(db, current_user)
