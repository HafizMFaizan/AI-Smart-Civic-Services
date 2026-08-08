"""Core entity and value objects for AI analysis of complaints."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class ComplaintCategory(str, Enum):
    ROAD = "Road"
    WATER = "Water"
    WASTE = "Waste"
    ELECTRICITY = "Electricity"
    DRAINAGE = "Drainage"
    SAFETY = "Safety"
    OTHER = "Other"


class ComplaintPriority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class AIStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class AIAnalysisResult:
    """Output of AIAnalyzer.analyze_complaint, before persistence."""

    category: ComplaintCategory
    priority: ComplaintPriority
    summary: str
    model_name: str
    ai_status: AIStatus
    confidence: Optional[float] = None


@dataclass
class AIAnalysis:
    """Persisted ai_analysis record."""

    complaint_id: int
    category: ComplaintCategory
    priority: ComplaintPriority
    summary: str
    model_name: str
    ai_status: AIStatus
    confidence: Optional[float] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_result(cls, complaint_id: int, result: AIAnalysisResult) -> "AIAnalysis":
        return cls(
            complaint_id=complaint_id,
            category=result.category,
            priority=result.priority,
            summary=result.summary,
            model_name=result.model_name,
            ai_status=result.ai_status,
            confidence=result.confidence,
        )
