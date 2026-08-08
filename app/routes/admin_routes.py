"""Admin-facing routes: complaint dashboard listing and status updates.

Per the explicit Phase 3 scope, DatabaseManager and NotificationManager are
called directly here (there is no dedicated AdminService in the
architecture) -- update_complaint_status() and notify() are used exactly as
specified. No SQL and no Gemini calls happen in this module itself.

PHASE 3 AUTHENTICATION LIMITATION: there is no password/session/token/OAuth
infrastructure anywhere in the model or schema. "Admin access" here is only
a minimal role check: the caller supplies their user id via the X-User-Id
header, and that user's `role` column is checked against 'admin'. This is
NOT real authentication -- it trusts whatever user id the client sends.
"""

import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from app.models.ai_analysis import ComplaintCategory, ComplaintPriority
from app.models.complaint import ComplaintStatus
from app.services.db_manager import UNANALYZED_LABEL, DatabaseError, DatabaseManager
from app.services.notification_manager import NotificationManager, NotificationManagerError

_VALID_CATEGORY_FILTERS = {category.value for category in ComplaintCategory} | {UNANALYZED_LABEL}
_VALID_PRIORITY_FILTERS = {priority.value for priority in ComplaintPriority} | {UNANALYZED_LABEL}

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

_db_manager: Optional[DatabaseManager] = None
_notification_manager: Optional[NotificationManager] = None


def init_app(db_manager: DatabaseManager, notification_manager: NotificationManager) -> None:
    global _db_manager, _notification_manager
    _db_manager = db_manager
    _notification_manager = notification_manager


def require_admin(x_user_id: Optional[int] = Header(default=None)) -> int:
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="Missing X-User-Id header.")
    try:
        role = _db_manager.get_user_role(x_user_id)
    except DatabaseError:
        logger.exception("Failed to verify role for user_id=%s", x_user_id)
        raise HTTPException(status_code=500, detail="Failed to verify admin access.")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required.")
    return x_user_id


class AdminComplaintResponse(BaseModel):
    complaint_id: int
    user_id: int
    citizen_name: str
    citizen_email: str
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


class StatusUpdateRequest(BaseModel):
    status: ComplaintStatus


class StatusUpdateResponse(BaseModel):
    complaint_id: int
    status: str
    notified_user_id: Optional[int]


@router.get("/admin/complaints", response_model=List[AdminComplaintResponse])
def list_all_complaints(
    admin_user_id: int = Depends(require_admin),
    category: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    status: Optional[ComplaintStatus] = Query(default=None),
    department_id: Optional[int] = Query(default=None),
    location: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
) -> List[AdminComplaintResponse]:
    if category is not None and category not in _VALID_CATEGORY_FILTERS:
        raise HTTPException(status_code=422, detail=f"Invalid category filter: {category!r}")
    if priority is not None and priority not in _VALID_PRIORITY_FILTERS:
        raise HTTPException(status_code=422, detail=f"Invalid priority filter: {priority!r}")

    try:
        rows = _db_manager.get_all_complaints(
            category=category,
            priority=priority,
            status=status.value if status is not None else None,
            department_id=department_id,
            location=location,
            search=search,
            date_from=date_from.isoformat() if date_from is not None else None,
            date_to=date_to.isoformat() if date_to is not None else None,
        )
    except DatabaseError:
        logger.exception("Failed to fetch all complaints.")
        raise HTTPException(status_code=500, detail="Failed to fetch complaints.")

    return [
        AdminComplaintResponse(
            complaint_id=row[0],
            user_id=row[1],
            citizen_name=row[2],
            citizen_email=row[3],
            description=row[4],
            location=row[5],
            status=row[6],
            department_id=row[7],
            assigned_department=row[8],
            category=row[9],
            priority=row[10],
            ai_summary=row[11],
            ai_status=row[12],
            date=str(row[13]) if row[13] is not None else None,
        )
        for row in rows
    ]


@router.patch("/admin/complaints/{complaint_id}/status", response_model=StatusUpdateResponse)
def update_complaint_status(
    complaint_id: int,
    payload: StatusUpdateRequest,
    admin_user_id: int = Depends(require_admin),
) -> StatusUpdateResponse:
    try:
        _db_manager.update_complaint_status(complaint_id, payload.status)
    except DatabaseError:
        logger.exception("Failed to update status for complaint_id=%s", complaint_id)
        raise HTTPException(
            status_code=404, detail="Complaint not found or could not be updated."
        )

    notified_user_id: Optional[int] = None
    try:
        owner_user_id = _db_manager.get_complaint_owner(complaint_id)
        if owner_user_id is not None:
            _notification_manager.notify(
                user_id=owner_user_id,
                message=f"Your complaint status was updated to '{payload.status.value}'.",
                complaint_id=complaint_id,
            )
            notified_user_id = owner_user_id
    except (DatabaseError, NotificationManagerError):
        # Status update already succeeded; a notification failure must not
        # undo it -- mirrors the AI/department fallback philosophy from
        # Phase 1/2, applied here to a secondary side effect.
        logger.exception(
            "Status updated for complaint_id=%s, but notifying the citizen failed.",
            complaint_id,
        )

    return StatusUpdateResponse(
        complaint_id=complaint_id,
        status=payload.status.value,
        notified_user_id=notified_user_id,
    )
