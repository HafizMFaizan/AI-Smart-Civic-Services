"""Complaint entity representing a citizen-submitted civic complaint with DevOps pipeline stages."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class ComplaintStatus(str, Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class PipelineStage(str, Enum):
    SUBMITTED = "submitted"
    AI_TRIAGED = "ai_triaged"
    DISPATCHED = "dispatched"
    IN_REPAIR = "in_repair"
    QUALITY_CHECK = "quality_check"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class Complaint:
    user_id: int
    description: str
    department_id: Optional[int] = None
    location: Optional[str] = None
    status: ComplaintStatus = ComplaintStatus.OPEN
    pipeline_stage: PipelineStage = PipelineStage.SUBMITTED
    sla_days: int = 7
    sla_due_date: Optional[datetime] = None
    sla_status: str = "on_time"
    department_remarks: Optional[str] = None
    rating_score: Optional[int] = None
    review_comment: Optional[str] = None
    image_url: Optional[str] = None
    id: Optional[int] = None
    resolved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    def update_status(self, new_status: ComplaintStatus) -> None:
        if not isinstance(new_status, ComplaintStatus):
            raise ValueError(f"Invalid complaint status: {new_status!r}")
        self.status = new_status

    def is_closed(self) -> bool:
        return self.status in (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED)
