"""Admin & Super Admin routes: RBAC management, application approval, and complaint status triage."""

import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from app.models.ai_analysis import ComplaintCategory, ComplaintPriority
from app.models.complaint import ComplaintStatus, PipelineStage
from app.services.complaint_manager import ComplaintManager, ComplaintManagerError
from app.services.db_manager import UNANALYZED_LABEL, DatabaseError, DatabaseManager
from app.services.notification_manager import NotificationManager, NotificationManagerError

_VALID_CATEGORY_FILTERS = {category.value for category in ComplaintCategory} | {UNANALYZED_LABEL}
_VALID_PRIORITY_FILTERS = {priority.value for priority in ComplaintPriority} | {UNANALYZED_LABEL}
_VALID_SLA_STATUS_FILTERS = {"on_time", "breached"}

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

_db_manager: Optional[DatabaseManager] = None
_notification_manager: Optional[NotificationManager] = None
_complaint_manager: Optional[ComplaintManager] = None


def init_app(
    db_manager: DatabaseManager,
    notification_manager: NotificationManager,
    complaint_manager: Optional[ComplaintManager] = None,
) -> None:
    global _db_manager, _notification_manager, _complaint_manager
    _db_manager = db_manager
    _notification_manager = notification_manager
    _complaint_manager = complaint_manager


def require_admin(x_user_id: Optional[int] = Header(default=None)) -> int:
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="Missing X-User-Id header.")
    try:
        role = _db_manager.get_user_role(x_user_id)
    except DatabaseError:
        raise HTTPException(status_code=500, detail="Failed to verify admin access.")
    if role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin or Super Admin role required.")
    return x_user_id


def require_super_admin(x_user_id: Optional[int] = Header(default=None)) -> int:
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="Missing X-User-Id header.")
    role = _db_manager.get_user_role(x_user_id)
    if role != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin role required.")
    return x_user_id


def require_permission(permission: str):
    """Builds a dependency gating on a specific RBAC permission.

    super_admin always bypasses (their permissions are conceptually "all").
    Regular admins must have the exact permission string in users.permissions.
    """

    def dependency(x_user_id: Optional[int] = Header(default=None)) -> int:
        require_admin(x_user_id)
        role = _db_manager.get_user_role(x_user_id)
        if role == "super_admin":
            return x_user_id
        try:
            permissions = _db_manager.get_user_permissions(x_user_id)
        except DatabaseError:
            raise HTTPException(status_code=500, detail="Failed to verify admin permissions.")
        if permission not in permissions:
            raise HTTPException(status_code=403, detail=f"Missing required permission: {permission!r}")
        return x_user_id

    return dependency


require_manage_complaints = require_permission("manage_complaints")
require_view_analytics = require_permission("view_analytics")


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
    pipeline_stage: Optional[str]
    sla_due_date: Optional[str]
    sla_status: Optional[str]


class StatusUpdateRequest(BaseModel):
    status: ComplaintStatus
    department_remarks: Optional[str] = None


class StatusUpdateResponse(BaseModel):
    complaint_id: int
    status: str
    notified_user_id: Optional[int]


class StageUpdateRequest(BaseModel):
    stage: PipelineStage


class StageUpdateResponse(BaseModel):
    complaint_id: int
    pipeline_stage: str
    notified_user_id: Optional[int]


@router.get("/admin/applications")
def get_admin_applications(super_admin_id: int = Depends(require_super_admin)):
    try:
        return _db_manager.get_pending_admin_applications()
    except DatabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/admin/applications/{app_id}/approve")
def approve_admin_application(app_id: int, super_admin_id: int = Depends(require_super_admin)):
    try:
        return _db_manager.approve_admin_application(app_id, super_admin_id)
    except DatabaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/admin/complaints", response_model=List[AdminComplaintResponse])
def list_all_complaints(
    admin_user_id: int = Depends(require_manage_complaints),
    category: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    status: Optional[ComplaintStatus] = Query(default=None),
    department_id: Optional[int] = Query(default=None),
    location: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    sla_status: Optional[str] = Query(default=None),
) -> List[AdminComplaintResponse]:
    if category is not None and category not in _VALID_CATEGORY_FILTERS:
        raise HTTPException(status_code=422, detail=f"Invalid category filter: {category!r}")
    if priority is not None and priority not in _VALID_PRIORITY_FILTERS:
        raise HTTPException(status_code=422, detail=f"Invalid priority filter: {priority!r}")
    if sla_status is not None and sla_status not in _VALID_SLA_STATUS_FILTERS:
        raise HTTPException(status_code=422, detail=f"Invalid sla_status filter: {sla_status!r}")

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
            sla_status=sla_status,
        )
    except DatabaseError:
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
            pipeline_stage=row[14],
            sla_due_date=str(row[15]) if row[15] is not None else None,
            sla_status=row[16],
        )
        for row in rows
    ]


@router.patch("/admin/complaints/{complaint_id}/status", response_model=StatusUpdateResponse)
def update_complaint_status(
    complaint_id: int,
    payload: StatusUpdateRequest,
    admin_user_id: int = Depends(require_manage_complaints),
) -> StatusUpdateResponse:
    try:
        _db_manager.update_complaint_status(complaint_id, payload.status, payload.department_remarks)
    except DatabaseError:
        raise HTTPException(status_code=404, detail="Complaint not found or could not be updated.")

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
        logger.exception("Status updated for complaint_id=%s, but notifying citizen failed.", complaint_id)

    return StatusUpdateResponse(
        complaint_id=complaint_id,
        status=payload.status.value,
        notified_user_id=notified_user_id,
    )


@router.patch("/admin/complaints/{complaint_id}/stage", response_model=StageUpdateResponse)
def advance_complaint_stage(
    complaint_id: int,
    payload: StageUpdateRequest,
    admin_user_id: int = Depends(require_manage_complaints),
) -> StageUpdateResponse:
    if _complaint_manager is None:
        raise HTTPException(status_code=500, detail="Pipeline stage advancement is not configured.")

    try:
        new_stage = _complaint_manager.advance_pipeline_stage(complaint_id, payload.stage)
    except ComplaintManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    notified_user_id: Optional[int] = None
    try:
        owner_user_id = _db_manager.get_complaint_owner(complaint_id)
        if owner_user_id is not None:
            _notification_manager.notify(
                user_id=owner_user_id,
                message=f"Your complaint has progressed to stage '{new_stage}'.",
                complaint_id=complaint_id,
            )
            notified_user_id = owner_user_id
    except (DatabaseError, NotificationManagerError):
        logger.exception("Stage updated for complaint_id=%s, but notifying citizen failed.", complaint_id)

    return StageUpdateResponse(
        complaint_id=complaint_id,
        pipeline_stage=new_stage,
        notified_user_id=notified_user_id,
    )
