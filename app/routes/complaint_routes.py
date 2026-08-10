"""Citizen-facing complaint routes.

Thin FastAPI layer only: no SQL and no Gemini calls happen here. Complaint
submission goes through ComplaintManager; complaint listing and notification
retrieval go through DatabaseManager / NotificationManager respectively.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.complaint_manager import ComplaintManager, ComplaintManagerError
from app.services.db_manager import DatabaseError, DatabaseManager
from app.services.notification_manager import NotificationManager, NotificationManagerError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["complaints"])

_complaint_manager: Optional[ComplaintManager] = None
_db_manager: Optional[DatabaseManager] = None
_notification_manager: Optional[NotificationManager] = None


def init_app(
    complaint_manager: ComplaintManager,
    db_manager: DatabaseManager,
    notification_manager: NotificationManager,
) -> None:
    global _complaint_manager, _db_manager, _notification_manager
    _complaint_manager = complaint_manager
    _db_manager = db_manager
    _notification_manager = notification_manager


class ComplaintSubmitRequest(BaseModel):
    user_id: int
    description: str = Field(min_length=1)
    location: Optional[str] = None
    department_id: Optional[int] = None
    context: Optional[Dict[str, Any]] = None


class ComplaintSubmitResponse(BaseModel):
    complaint_id: int
    department_id: Optional[int]
    ai_status: str
    category: str
    priority: str


class CitizenComplaintResponse(BaseModel):
    complaint_id: int
    description: str
    location: Optional[str]
    status: str
    department_id: Optional[int]
    assigned_department: Optional[str]
    category: Optional[str]
    priority: Optional[str]
    ai_summary: Optional[str]
    ai_status: Optional[str]
    date: Optional[str]
    pipeline_stage: Optional[str]
    sla_days: Optional[int]
    sla_due_date: Optional[str]
    department_remarks: Optional[str]
    sla_status: Optional[str]


class DepartmentResponse(BaseModel):
    department_id: int
    name: str
    category: str


class NotificationResponse(BaseModel):
    id: Optional[int]
    complaint_id: Optional[int]
    message: str
    is_read: bool
    created_at: Optional[str]


class NotificationReadResponse(BaseModel):
    notification_id: int
    is_read: bool


@router.post("/complaints", response_model=ComplaintSubmitResponse, status_code=201)
def submit_complaint(payload: ComplaintSubmitRequest) -> ComplaintSubmitResponse:
    if payload.department_id is not None:
        try:
            department_id_exists = _db_manager.department_exists(payload.department_id)
        except DatabaseError:
            logger.exception(
                "Failed to validate department_id=%s for user_id=%s",
                payload.department_id,
                payload.user_id,
            )
            raise HTTPException(
                status_code=500, detail="Failed to submit complaint. Please try again later."
            )
        if not department_id_exists:
            raise HTTPException(
                status_code=422,
                detail=f"department_id {payload.department_id} does not exist.",
            )

    try:
        result = _complaint_manager.submit_complaint(
            user_id=payload.user_id,
            description=payload.description,
            department_id=payload.department_id,
            location=payload.location,
            context=payload.context,
        )
    except ComplaintManagerError:
        logger.exception("Failed to submit complaint for user_id=%s", payload.user_id)
        raise HTTPException(
            status_code=500, detail="Failed to submit complaint. Please try again later."
        )

    return ComplaintSubmitResponse(**result)


@router.get("/citizens/{user_id}/complaints", response_model=List[CitizenComplaintResponse])
def get_citizen_complaints(user_id: int) -> List[CitizenComplaintResponse]:
    try:
        rows = _db_manager.get_complaints_for_user(user_id)
    except DatabaseError:
        logger.exception("Failed to fetch complaints for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail="Failed to fetch complaints.")

    return [
        CitizenComplaintResponse(
            complaint_id=row[0],
            description=row[1],
            location=row[2],
            status=row[3],
            department_id=row[4],
            assigned_department=row[5],
            category=row[6],
            priority=row[7],
            ai_summary=row[8],
            ai_status=row[9],
            date=str(row[10]) if row[10] is not None else None,
            pipeline_stage=row[11],
            sla_days=row[12],
            sla_due_date=str(row[13]) if row[13] is not None else None,
            department_remarks=row[14],
            sla_status=row[15],
        )
        for row in rows
    ]


@router.get("/departments", response_model=List[DepartmentResponse])
def list_departments() -> List[DepartmentResponse]:
    try:
        rows = _db_manager.get_all_departments()
    except DatabaseError:
        logger.exception("Failed to fetch departments.")
        raise HTTPException(status_code=500, detail="Failed to fetch departments.")

    return [DepartmentResponse(department_id=row[0], name=row[1], category=row[2]) for row in rows]


@router.get("/citizens/{user_id}/notifications", response_model=List[NotificationResponse])
def get_citizen_notifications(user_id: int) -> List[NotificationResponse]:
    try:
        notifications = _notification_manager.get_notifications_for_user(user_id)
    except NotificationManagerError:
        logger.exception("Failed to fetch notifications for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail="Failed to fetch notifications.")

    return [
        NotificationResponse(
            id=n.id,
            complaint_id=n.complaint_id,
            message=n.message,
            is_read=n.is_read,
            created_at=str(n.created_at) if n.created_at is not None else None,
        )
        for n in notifications
    ]


@router.patch("/notifications/{notification_id}/read", response_model=NotificationReadResponse)
def mark_notification_read(notification_id: int) -> NotificationReadResponse:
    try:
        _notification_manager.mark_as_read(notification_id)
    except NotificationManagerError:
        logger.exception("Failed to mark notification_id=%s as read", notification_id)
        raise HTTPException(status_code=404, detail="Notification not found.")

    return NotificationReadResponse(notification_id=notification_id, is_read=True)
