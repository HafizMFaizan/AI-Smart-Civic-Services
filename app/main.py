"""FastAPI application entrypoint.

Constructs the service layer exactly once (DatabaseManager, AIAnalyzer,
ComplaintManager, AnalyticsService, NotificationManager) and wires it into
the route modules -- no route handler ever constructs its own service
instance. Static frontend files are served from app/static.
"""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import admin_routes, analytics_routes, complaint_routes, user_routes
from app.services.ai_service import AIAnalyzer
from app.services.analytics_service import AnalyticsService
from app.services.complaint_manager import ComplaintManager
from app.services.db_manager import DatabaseManager
from app.services.notification_manager import NotificationManager

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(
    db_manager: Optional[DatabaseManager] = None,
    ai_service: Optional[AIAnalyzer] = None,
) -> FastAPI:
    """Build a fully-wired FastAPI app.

    Accepts optional pre-built db_manager/ai_service so tests can point the
    app at an isolated temp database and a mocked Gemini client instead of
    the real ones used at runtime.
    """
    db_manager = db_manager or DatabaseManager()
    db_manager.initialize_database()

    ai_service = ai_service or AIAnalyzer()
    notification_manager = NotificationManager(db_manager=db_manager)
    complaint_manager = ComplaintManager(
        db_manager=db_manager, ai_service=ai_service, notification_manager=notification_manager
    )
    analytics_service = AnalyticsService(db_manager=db_manager)

    complaint_routes.init_app(
        complaint_manager=complaint_manager,
        db_manager=db_manager,
        notification_manager=notification_manager,
    )
    admin_routes.init_app(
        db_manager=db_manager,
        notification_manager=notification_manager,
        complaint_manager=complaint_manager,
    )
    analytics_routes.init_app(analytics_service=analytics_service)
    user_routes.init_app(db_manager=db_manager)

    fastapi_app = FastAPI(title="AI Smart Civic Services", version="0.3.0")

    fastapi_app.include_router(complaint_routes.router, prefix="/api")
    fastapi_app.include_router(admin_routes.router, prefix="/api")
    fastapi_app.include_router(analytics_routes.router, prefix="/api")
    fastapi_app.include_router(user_routes.router, prefix="/api")

    @fastapi_app.get("/api/health", tags=["health"])
    def health_check() -> dict:
        return {"status": "ok"}

    fastapi_app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return fastapi_app


app = create_app()
