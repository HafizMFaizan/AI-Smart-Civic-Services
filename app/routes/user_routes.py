"""User authentication, registration, and city health routes."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.db_manager import DatabaseError, DatabaseManager, DuplicateEmailError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["users", "auth"])

_db_manager: Optional[DatabaseManager] = None


def init_app(db_manager: DatabaseManager) -> None:
    global _db_manager
    _db_manager = db_manager


class UserRegisterRequest(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(default="password123", min_length=4)
    phone: Optional[str] = None


class UserLoginRequest(BaseModel):
    email: str
    password: str


class AdminApplicationRequest(BaseModel):
    user_id: int
    department_name: str = "General Triage"
    reason: str = "Municipal Officer Application"


@router.post("/auth/signup", status_code=201)
@router.post("/users", status_code=201)
def register_user(payload: UserRegisterRequest):
    try:
        user_id = _db_manager.register_user(
            name=payload.name, email=payload.email, password=payload.password, phone=payload.phone, role="citizen"
        )
    except DuplicateEmailError:
        raise HTTPException(status_code=409, detail="Email already registered.")
    except DatabaseError:
        raise HTTPException(status_code=500, detail="Failed to register user.")

    return {"user_id": user_id, "name": payload.name, "email": payload.email, "role": "citizen", "message": "Account created successfully."}


@router.post("/auth/login")
def login_user(payload: UserLoginRequest):
    user = _db_manager.authenticate_user(email=payload.email, password=payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {"status": "authenticated", "user": user}


@router.get("/city-health")
def get_city_health():
    if not _db_manager:
        return {"risk_level": "GREEN", "description": "Normal Operations"}
    return _db_manager.get_city_health_risk()


@router.post("/admin-applications", status_code=201)
def apply_for_admin(payload: AdminApplicationRequest):
    try:
        app_id = _db_manager.create_admin_application(
            user_id=payload.user_id,
            department_name=payload.department_name,
            reason=payload.reason
        )
        return {"application_id": app_id, "status": "pending", "message": "Admin application submitted. Pending Super Admin approval."}
    except DatabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
