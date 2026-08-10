"""ComplaintManager: orchestrates end-to-end complaint submission, AI triage, SLA calculation, and SMS dispatches."""

import logging
from typing import Any, Optional

from app.models.ai_analysis import AIAnalysis, ComplaintPriority
from app.models.complaint import PipelineStage
from app.models.department import Department
from app.services.ai_service import AIAnalyzer
from app.services.db_manager import DatabaseError, DatabaseManager
from app.services.notification_manager import NotificationManager, NotificationManagerError

logger = logging.getLogger(__name__)

# Forward-only internal stages an admin can advance a complaint through.
# 'resolved'/'closed' are deliberately excluded -- those go through
# update_complaint_status(), which also runs the SLA breach/remarks logic.
_ADVANCEABLE_STAGE_ORDER = [
    PipelineStage.SUBMITTED,
    PipelineStage.AI_TRIAGED,
    PipelineStage.DISPATCHED,
    PipelineStage.IN_REPAIR,
    PipelineStage.QUALITY_CHECK,
]


class ComplaintManagerError(Exception):
    """Raised when complaint orchestration fails."""


class ComplaintManager:
    def __init__(
        self,
        db_manager: DatabaseManager,
        ai_service: AIAnalyzer,
        notification_manager: Optional[NotificationManager] = None,
    ) -> None:
        self._db_manager = db_manager
        self._ai_service = ai_service
        self._notification_manager = notification_manager

    def submit_complaint(
        self,
        user_id: int,
        description: str,
        department_id: Optional[int] = None,
        location: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:


        # 2. Analyze via AI
        ai_result = self._ai_service.analyze_complaint(description, context)
        
        # Determine SLA days (Req #10)
        sla_map = {"Critical": 2, "High": 4, "Medium": 7, "Low": 14}
        sla_days = sla_map.get(ai_result.priority.value, 7)

        # 3. Save complaint
        try:
            complaint_id = self._db_manager.save_complaint(
                user_id=user_id,
                description=description,
                department_id=department_id,
                location=location,
                sla_days=sla_days,
            )
        except DatabaseError as exc:
            raise ComplaintManagerError(f"Failed to save complaint: {exc}") from exc

        # 4. Save AI Analysis
        analysis = AIAnalysis.from_result(complaint_id=complaint_id, result=ai_result)
        try:
            self._db_manager.save_ai_analysis(analysis)
        except DatabaseError as exc:
            logger.exception("AI analysis save failed for complaint %s", complaint_id)

        # 5. Department Auto Routing (Req #7)
        department_name = "General Triage"
        if department_id is None:
            try:
                department_name = Department.name_for_category(analysis.category)
                resolved_department_id = self._db_manager.get_or_create_department(
                    name=department_name, category=analysis.category
                )
                self._db_manager.update_complaint_department(complaint_id, resolved_department_id)
                department_id = resolved_department_id
            except DatabaseError:
                logger.exception("Automatic department assignment failed for complaint %s", complaint_id)



        is_critical = (analysis.priority.value == "Critical")
        if is_critical and self._notification_manager is not None:
            self._broadcast_critical_alert(complaint_id, user_id, location, department_name)

        return {
            "complaint_id": complaint_id,
            "department_id": department_id,
            "department_name": department_name,
            "ai_status": analysis.ai_status.value,
            "category": analysis.category.value,
            "priority": analysis.priority.value,
            "sla_days": sla_days,
            "is_critical": is_critical,
            "pipeline_stage": "ai_triaged",
        }

    def _broadcast_critical_alert(
        self, complaint_id: int, citizen_user_id: int, location: Optional[str], department_name: str
    ) -> None:
        alert_message = (
            f"CRITICAL complaint #{complaint_id} reported at "
            f"{location or 'an unspecified location'} and routed to {department_name}. "
            "Immediate attention required."
        )
        try:
            admin_ids = self._db_manager.get_admin_user_ids()
        except DatabaseError:
            logger.exception("Failed to fetch admin ids for critical alert on complaint %s", complaint_id)
            admin_ids = []

        for admin_id in admin_ids:
            try:
                self._notification_manager.notify(
                    user_id=admin_id, message=alert_message, complaint_id=complaint_id
                )
            except NotificationManagerError:
                logger.exception(
                    "Failed to notify admin_id=%s of critical complaint %s", admin_id, complaint_id
                )

        try:
            self._notification_manager.notify(
                user_id=citizen_user_id,
                message="Your complaint has been flagged CRITICAL and escalated for immediate action.",
                complaint_id=complaint_id,
            )
        except NotificationManagerError:
            logger.exception(
                "Failed to notify citizen user_id=%s of critical escalation for complaint %s",
                citizen_user_id,
                complaint_id,
            )

    def advance_pipeline_stage(self, complaint_id: int, target_stage: PipelineStage) -> str:
        if target_stage not in _ADVANCEABLE_STAGE_ORDER:
            raise ComplaintManagerError(
                f"Stage {target_stage.value!r} must be set via the complaint status endpoint, not pipeline advancement."
            )

        try:
            current_value = self._db_manager.get_complaint_pipeline_stage(complaint_id)
        except DatabaseError as exc:
            raise ComplaintManagerError(f"Failed to read current pipeline stage: {exc}") from exc

        if current_value is None:
            raise ComplaintManagerError(f"No complaint found with id {complaint_id}.")

        try:
            current_stage = PipelineStage(current_value)
        except ValueError:
            current_stage = None

        if current_stage not in _ADVANCEABLE_STAGE_ORDER:
            raise ComplaintManagerError(
                f"Complaint {complaint_id} is already at stage {current_value!r} and cannot be advanced further."
            )

        current_index = _ADVANCEABLE_STAGE_ORDER.index(current_stage)
        target_index = _ADVANCEABLE_STAGE_ORDER.index(target_stage)
        if target_index != current_index + 1:
            raise ComplaintManagerError(
                f"Cannot advance from {current_stage.value!r} directly to {target_stage.value!r}; "
                f"the next valid stage is {_ADVANCEABLE_STAGE_ORDER[current_index + 1].value!r}."
                if current_index + 1 < len(_ADVANCEABLE_STAGE_ORDER)
                else f"Complaint {complaint_id} has no further advanceable stage; use the status endpoint to resolve it."
            )

        try:
            self._db_manager.update_complaint_pipeline_stage(complaint_id, target_stage.value)
        except DatabaseError as exc:
            raise ComplaintManagerError(f"Failed to update pipeline stage: {exc}") from exc

        return target_stage.value
