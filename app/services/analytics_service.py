"""AnalyticsService: foundation for complaint dashboard statistics.

Reads structured complaint/AI data via DatabaseManager and shapes it into
consistent aggregates. No charting or presentation logic lives here.
"""

from typing import Dict, List, Optional

from app.models.ai_analysis import ComplaintCategory, ComplaintPriority
from app.models.complaint import ComplaintStatus
from app.services.db_manager import (
    UNANALYZED_LABEL,
    UNASSIGNED_DEPARTMENT_LABEL,
    DatabaseError,
    DatabaseManager,
)


class AnalyticsServiceError(Exception):
    """Raised when an analytics calculation fails."""


class AnalyticsService:
    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db_manager = db_manager

    def total_complaints(self) -> int:
        try:
            return self._db_manager.count_total_complaints()
        except DatabaseError as exc:
            raise AnalyticsServiceError(f"Failed to compute total complaints: {exc}") from exc

    def complaints_by_category(self) -> Dict[str, int]:
        # Complaints with no ai_analysis row yet are bucketed under
        # UNANALYZED_LABEL rather than omitted, so this reconciles with total_complaints().
        try:
            counts = self._db_manager.count_complaints_by_category()
        except DatabaseError as exc:
            raise AnalyticsServiceError(
                f"Failed to compute complaints by category: {exc}"
            ) from exc
        defaults = {category.value: 0 for category in ComplaintCategory}
        defaults[UNANALYZED_LABEL] = 0
        return self._with_zero_defaults(defaults, counts)

    def complaints_by_priority(self) -> Dict[str, int]:
        # Same UNANALYZED_LABEL bucket as complaints_by_category().
        try:
            counts = self._db_manager.count_complaints_by_priority()
        except DatabaseError as exc:
            raise AnalyticsServiceError(
                f"Failed to compute complaints by priority: {exc}"
            ) from exc
        defaults = {priority.value: 0 for priority in ComplaintPriority}
        defaults[UNANALYZED_LABEL] = 0
        return self._with_zero_defaults(defaults, counts)

    def complaints_by_status(self) -> Dict[str, int]:
        try:
            counts = self._db_manager.count_complaints_by_status()
        except DatabaseError as exc:
            raise AnalyticsServiceError(
                f"Failed to compute complaints by status: {exc}"
            ) from exc
        return self._with_zero_defaults(
            {status.value: 0 for status in ComplaintStatus}, counts
        )

    def complaints_by_department(self) -> Dict[str, int]:
        # Complaints with no department yet are bucketed under UNASSIGNED_DEPARTMENT_LABEL.
        try:
            counts = self._db_manager.count_complaints_by_department()
        except DatabaseError as exc:
            raise AnalyticsServiceError(
                f"Failed to compute complaints by department: {exc}"
            ) from exc
        return self._with_zero_defaults({UNASSIGNED_DEPARTMENT_LABEL: 0}, counts)

    def complaint_trends(self, group_by: str) -> List[Dict[str, object]]:
        try:
            rows = self._db_manager.get_complaint_trends(group_by)
        except DatabaseError as exc:
            raise AnalyticsServiceError(f"Failed to compute complaint trends: {exc}") from exc
        return [{"period": period, "count": count} for period, count in rows]

    def active_sla_breaches(self) -> int:
        try:
            return self._db_manager.count_active_sla_breaches()
        except DatabaseError as exc:
            raise AnalyticsServiceError(f"Failed to compute active SLA breaches: {exc}") from exc

    def resolution_time_stats(self) -> Dict[str, Optional[float]]:
        try:
            avg_hours, min_hours, max_hours, resolved_count = (
                self._db_manager.get_resolution_time_stats()
            )
        except DatabaseError as exc:
            raise AnalyticsServiceError(
                f"Failed to compute resolution time stats: {exc}"
            ) from exc
        return {
            "average_hours": round(avg_hours, 2) if avg_hours is not None else None,
            "minimum_hours": round(min_hours, 2) if min_hours is not None else None,
            "maximum_hours": round(max_hours, 2) if max_hours is not None else None,
            "resolved_count": resolved_count,
        }

    @staticmethod
    def _with_zero_defaults(defaults: Dict[str, int], counts: Dict[str, int]) -> Dict[str, int]:
        result = dict(defaults)
        result.update(counts)
        return result
