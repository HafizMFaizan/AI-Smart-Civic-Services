"""ComplaintManager: orchestrates end-to-end complaint submission, AI triage, SLA calculation, and SMS dispatches."""

import logging
from typing import Any, Optional

from app.models.ai_analysis import AIAnalysis, ComplaintPriority
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
