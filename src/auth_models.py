"""Pydantic schemas for the auth API.

These are intentionally separate from :mod:`src.db_models` (SQLAlchemy ORM)
so the wire format and the storage format can evolve independently.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Payload for ``POST /api/auth/register``."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=120)


class UserLogin(BaseModel):
    """Payload for ``POST /api/auth/login``."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class WorkspaceOut(BaseModel):
    """A workspace as exposed to the API client."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    plan: str
    created_at: datetime


class UserOut(BaseModel):
    """The currently-authenticated user, returned by ``GET /api/auth/me``.

    Includes the personal workspace so the client can render workspace-scoped
    UI without a second round-trip.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    display_name: str
    is_active: bool
    is_superuser: bool
    created_at: datetime
    personal_workspace: WorkspaceOut


class AuthResponse(BaseModel):
    """Returned by register/login. The token also lands in an httpOnly cookie."""

    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MessageResponse(BaseModel):
    message: str
