"""Department entity and its deterministic mapping from complaint category.

Department assignment is never delegated to Gemini -- the mapping below is
fixed and owned entirely by this module.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from app.models.ai_analysis import ComplaintCategory

CATEGORY_TO_DEPARTMENT_NAME: Dict[ComplaintCategory, str] = {
    ComplaintCategory.ROAD: "Road Maintenance",
    ComplaintCategory.WATER: "Water & Sewerage",
    ComplaintCategory.WASTE: "Waste Management",
    ComplaintCategory.ELECTRICITY: "Electricity",
    ComplaintCategory.DRAINAGE: "Drainage",
    ComplaintCategory.SAFETY: "Public Safety",
    ComplaintCategory.OTHER: "General Services",
}


@dataclass
class Department:
    name: str
    category: ComplaintCategory
    id: Optional[int] = None
    created_at: Optional[datetime] = None

    @staticmethod
    def name_for_category(category: ComplaintCategory) -> str:
        return CATEGORY_TO_DEPARTMENT_NAME[category]
