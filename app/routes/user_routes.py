"""User registration routes.

Public and unauthenticated by necessity -- a brand-new citizen has no
user_id yet to prove anything with. Always creates role='citizen' on the
server side; never accepts a client-supplied role, since this endpoint has
no authentication and must not let a caller self-promote to admin.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.db_manager import DatabaseError, DatabaseManager, DuplicateEmailError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["users"])

_db_manager: Optional[DatabaseManager] = None


def init_app(db_manager: DatabaseManager) -> None:
    global _db_manager
    _db_manager = db_manager


class UserRegisterRequest(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    phone: Optional[str] = None


class UserRegisterResponse(BaseModel):
    user_id: int
    name: str
    email: str
    role: str


@router.post("/users", response_model=UserRegisterResponse, status_code=201)
def register_user(payload: UserRegisterRequest) -> UserRegisterResponse:
    try:
        user_id = _db_manager.create_user(
            name=payload.name, email=payload.email, phone=payload.phone
        )
    except DuplicateEmailError:
        raise HTTPException(status_code=409, detail="Email already registered.")
    except DatabaseError:
        logger.exception("Failed to register user with email=%s", payload.email)
        raise HTTPException(
            status_code=500, detail="Failed to register user. Please try again later."
        )

    return UserRegisterResponse(user_id=user_id, name=payload.name, email=payload.email, role="citizen")
