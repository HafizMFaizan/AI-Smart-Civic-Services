"""Complaint entity representing a citizen-submitted civic complaint."""

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


@dataclass
class Complaint:
    user_id: int
    description: str
    department_id: Optional[int] = None
    location: Optional[str] = None
    status: ComplaintStatus = ComplaintStatus.OPEN
    id: Optional[int] = None
    resolved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    def update_status(self, new_status: ComplaintStatus) -> None:
        if not isinstance(new_status, ComplaintStatus):
            raise ValueError(f"Invalid complaint status: {new_status!r}")
        self.status = new_status

    def is_closed(self) -> bool:
        return self.status in (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED)
