"""ComplaintManager: orchestrates complaint submission end to end.

The complaint is always saved first and independently of AI outcome.
AIAnalyzer never raises to this layer -- it returns a fallback result on
failure -- so an AI failure can never prevent or delete a saved complaint.
Department assignment uses the deterministic category mapping in
app.models.department -- Gemini is never asked to pick a department.

AI analysis is persisted before department assignment is attempted, so a
department-assignment failure (a DatabaseManager-level error, distinct from
an AI failure) can never discard an already-successful AI result. If
automatic department assignment fails, the complaint and its AI analysis
are preserved and the complaint is simply left unassigned.
"""

import logging
from typing import Any, Optional

from app.models.ai_analysis import AIAnalysis
from app.models.department import Department
from app.services.ai_service import AIAnalyzer
from app.services.db_manager import DatabaseError, DatabaseManager

logger = logging.getLogger(__name__)


class ComplaintManagerError(Exception):
    """Raised when complaint orchestration fails."""


class ComplaintManager:
    def __init__(self, db_manager: DatabaseManager, ai_service: AIAnalyzer) -> None:
        self._db_manager = db_manager
        self._ai_service = ai_service

    def submit_complaint(
        self,
        user_id: int,
        description: str,
        department_id: Optional[int] = None,
        location: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        try:
            complaint_id = self._db_manager.save_complaint(
                user_id=user_id,
                description=description,
                department_id=department_id,
                location=location,
            )
        except DatabaseError as exc:
            raise ComplaintManagerError(f"Failed to save complaint: {exc}") from exc

        ai_result = self._ai_service.analyze_complaint(description, context)
        analysis = AIAnalysis.from_result(complaint_id=complaint_id, result=ai_result)

        try:
            self._db_manager.save_ai_analysis(analysis)
        except DatabaseError as exc:
            raise ComplaintManagerError(
                f"Complaint {complaint_id} saved, but AI analysis could not be "
                f"persisted: {exc}"
            ) from exc

        if department_id is None:
            try:
                department_name = Department.name_for_category(analysis.category)
                resolved_department_id = self._db_manager.get_or_create_department(
                    name=department_name, category=analysis.category
                )
                self._db_manager.update_complaint_department(
                    complaint_id, resolved_department_id
                )
                department_id = resolved_department_id
            except DatabaseError:
                logger.exception(
                    "Complaint %s saved with AI analysis, but automatic department "
                    "assignment failed; leaving complaint unassigned.",
                    complaint_id,
                )

        return {
            "complaint_id": complaint_id,
            "department_id": department_id,
            "ai_status": analysis.ai_status.value,
            "category": analysis.category.value,
            "priority": analysis.priority.value,
        }
