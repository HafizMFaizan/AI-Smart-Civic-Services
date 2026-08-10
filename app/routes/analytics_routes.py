"""Analytics routes: thin FastAPI layer over AnalyticsService.

Every AnalyticsService method is exposed as-is; the "Unassigned" and
"Unanalyzed" buckets from Phase 2 pass straight through the Dict[str, int]
response fields without being filtered or renamed.

Gated by the "view_analytics" permission (X-User-Id + users.permissions),
reusing the same require_permission dependency factory admin_routes.py
builds its own checks from -- not duplicated. super_admin always bypasses.
This is still not real session-based authentication, just header-trusted
identity, per the Phase 3 limitation.
"""

import logging
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routes.admin_routes import require_view_analytics
from app.services.analytics_service import AnalyticsService, AnalyticsServiceError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])

_analytics_service: Optional[AnalyticsService] = None


def init_app(analytics_service: AnalyticsService) -> None:
    global _analytics_service
    _analytics_service = analytics_service


class AnalyticsDashboardResponse(BaseModel):
    total_complaints: int
    by_category: Dict[str, int]
    by_priority: Dict[str, int]
    by_status: Dict[str, int]
    by_department: Dict[str, int]
    active_sla_breaches: int


class TrendPoint(BaseModel):
    period: str
    count: int


class TrendsResponse(BaseModel):
    group_by: str
    series: List[TrendPoint]


class ResolutionTimeResponse(BaseModel):
    average_hours: Optional[float]
    minimum_hours: Optional[float]
    maximum_hours: Optional[float]
    resolved_count: int


@router.get("/analytics/dashboard", response_model=AnalyticsDashboardResponse)
def get_analytics_dashboard(
    admin_user_id: int = Depends(require_view_analytics),
) -> AnalyticsDashboardResponse:
    try:
        return AnalyticsDashboardResponse(
            total_complaints=_analytics_service.total_complaints(),
            by_category=_analytics_service.complaints_by_category(),
            by_priority=_analytics_service.complaints_by_priority(),
            by_status=_analytics_service.complaints_by_status(),
            by_department=_analytics_service.complaints_by_department(),
            active_sla_breaches=_analytics_service.active_sla_breaches(),
        )
    except AnalyticsServiceError:
        logger.exception("Failed to compute analytics dashboard.")
        raise HTTPException(status_code=500, detail="Failed to compute analytics.")


@router.get("/analytics/trends", response_model=TrendsResponse)
def get_complaint_trends(
    group_by: Literal["day", "week", "month"] = "day",
    admin_user_id: int = Depends(require_view_analytics),
) -> TrendsResponse:
    try:
        series = _analytics_service.complaint_trends(group_by)
    except AnalyticsServiceError:
        logger.exception("Failed to compute complaint trends.")
        raise HTTPException(status_code=500, detail="Failed to compute complaint trends.")
    return TrendsResponse(group_by=group_by, series=[TrendPoint(**point) for point in series])


@router.get("/analytics/resolution-time", response_model=ResolutionTimeResponse)
def get_resolution_time(
    admin_user_id: int = Depends(require_view_analytics),
) -> ResolutionTimeResponse:
    try:
        stats = _analytics_service.resolution_time_stats()
    except AnalyticsServiceError:
        logger.exception("Failed to compute resolution time stats.")
        raise HTTPException(status_code=500, detail="Failed to compute resolution time stats.")
    return ResolutionTimeResponse(**stats)
