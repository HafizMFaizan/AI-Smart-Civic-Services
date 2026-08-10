"""Tests for the SLA breach engine, pipeline stage advancement, and the
critical-priority admin alert broadcast.

DatabaseManager-level tests use a real temporary SQLite file directly.
API-level tests use FastAPI's TestClient against an isolated app built via
create_app(). No Gemini network access or real API key is required anywhere.
"""

import os
import sqlite3
import tempfile
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.complaint import ComplaintStatus, PipelineStage
from app.services.ai_service import AIAnalyzer
from app.services.complaint_manager import ComplaintManager, ComplaintManagerError
from app.services.db_manager import DatabaseManager
from app.services.notification_manager import NotificationManager


@pytest.fixture
def temp_db_path():
    path = os.path.join(tempfile.gettempdir(), f"sla_pipeline_test_{uuid.uuid4().hex}.db")
    if os.path.exists(path):
        os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def _seed_users(db_path: str) -> dict:
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()
    conn = sqlite3.connect(db_path)
    citizen_id = conn.execute(
        "INSERT INTO users (name, email, role) VALUES ('Citizen One', 'citizen1@example.com', 'citizen')"
    ).lastrowid
    admin_id = conn.execute(
        "INSERT INTO users (name, email, role, permissions) VALUES "
        "('Admin One', 'admin1@example.com', 'admin', '[\"manage_complaints\", \"view_analytics\"]')"
    ).lastrowid
    super_admin_id = conn.execute(
        "INSERT INTO users (name, email, role, permissions) VALUES "
        "('Super Admin', 'super1@example.com', 'super_admin', '[\"all\"]')"
    ).lastrowid
    conn.commit()
    conn.close()
    return {"citizen_id": citizen_id, "admin_id": admin_id, "super_admin_id": super_admin_id}


def _make_ai_service(response_text: str) -> AIAnalyzer:
    client = MagicMock()
    response = MagicMock()
    response.text = response_text
    client.models.generate_content.return_value = response
    return AIAnalyzer(client=client)


def _build_client(db_path: str, ai_service: AIAnalyzer) -> TestClient:
    db_manager = DatabaseManager(db_path=db_path)
    app = create_app(db_manager=db_manager, ai_service=ai_service)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Live SLA breach detection
# ---------------------------------------------------------------------------


def test_open_complaint_past_due_date_reports_breached(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    complaint_id = db_manager.save_complaint(
        user_id=users["citizen_id"], description="Still open", sla_days=1
    )

    conn = sqlite3.connect(temp_db_path)
    conn.execute(
        "UPDATE complaints SET sla_due_date = '2000-01-01 00:00:00' WHERE id = ?", (complaint_id,)
    )
    conn.commit()
    conn.close()

    rows = db_manager.get_all_complaints()
    assert len(rows) == 1
    assert rows[0][0] == complaint_id
    assert rows[0][16] == "breached"


def test_open_complaint_within_due_date_reports_on_time(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    db_manager.save_complaint(user_id=users["citizen_id"], description="Fresh", sla_days=14)

    rows = db_manager.get_all_complaints()
    assert rows[0][16] == "on_time"


def test_resolved_complaint_keeps_persisted_sla_status_not_live_recompute(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    complaint_id = db_manager.save_complaint(
        user_id=users["citizen_id"], description="Resolved late", sla_days=1
    )
    conn = sqlite3.connect(temp_db_path)
    conn.execute(
        "UPDATE complaints SET sla_due_date = '2000-01-01 00:00:00' WHERE id = ?", (complaint_id,)
    )
    conn.commit()
    conn.close()

    db_manager.update_complaint_status(complaint_id, ComplaintStatus.RESOLVED)

    rows = db_manager.get_all_complaints()
    assert rows[0][6] == "resolved"
    assert rows[0][16] == "breached"


def test_filter_by_sla_status_breached(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    breached_id = db_manager.save_complaint(user_id=users["citizen_id"], description="Late", sla_days=1)
    db_manager.save_complaint(user_id=users["citizen_id"], description="On time", sla_days=14)

    conn = sqlite3.connect(temp_db_path)
    conn.execute(
        "UPDATE complaints SET sla_due_date = '2000-01-01 00:00:00' WHERE id = ?", (breached_id,)
    )
    conn.commit()
    conn.close()

    breached_rows = db_manager.get_all_complaints(sla_status="breached")
    on_time_rows = db_manager.get_all_complaints(sla_status="on_time")

    assert len(breached_rows) == 1
    assert breached_rows[0][0] == breached_id
    assert len(on_time_rows) == 1


def test_count_active_sla_breaches(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    breached_id = db_manager.save_complaint(user_id=users["citizen_id"], description="Late", sla_days=1)
    db_manager.save_complaint(user_id=users["citizen_id"], description="On time", sla_days=14)

    conn = sqlite3.connect(temp_db_path)
    conn.execute(
        "UPDATE complaints SET sla_due_date = '2000-01-01 00:00:00' WHERE id = ?", (breached_id,)
    )
    conn.commit()
    conn.close()

    assert db_manager.count_active_sla_breaches() == 1

    db_manager.update_complaint_status(breached_id, ComplaintStatus.RESOLVED)
    assert db_manager.count_active_sla_breaches() == 0


def test_get_admin_user_ids_excludes_citizens(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)

    admin_ids = set(db_manager.get_admin_user_ids())
    assert {users["admin_id"], users["super_admin_id"]} <= admin_ids
    assert users["citizen_id"] not in admin_ids


# ---------------------------------------------------------------------------
# Pipeline stage advancement
# ---------------------------------------------------------------------------


def test_advance_pipeline_stage_valid_forward_transition(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    complaint_id = db_manager.save_complaint(user_id=users["citizen_id"], description="Pothole")

    manager = ComplaintManager(db_manager=db_manager, ai_service=_make_ai_service("{}"))
    result = manager.advance_pipeline_stage(complaint_id, PipelineStage.AI_TRIAGED)

    assert result == "ai_triaged"
    assert db_manager.get_complaint_pipeline_stage(complaint_id) == "ai_triaged"


def test_advance_pipeline_stage_rejects_skipping_a_stage(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    complaint_id = db_manager.save_complaint(user_id=users["citizen_id"], description="Pothole")

    manager = ComplaintManager(db_manager=db_manager, ai_service=_make_ai_service("{}"))
    with pytest.raises(ComplaintManagerError):
        manager.advance_pipeline_stage(complaint_id, PipelineStage.DISPATCHED)


def test_advance_pipeline_stage_rejects_resolved_target(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    complaint_id = db_manager.save_complaint(user_id=users["citizen_id"], description="Pothole")

    manager = ComplaintManager(db_manager=db_manager, ai_service=_make_ai_service("{}"))
    with pytest.raises(ComplaintManagerError):
        manager.advance_pipeline_stage(complaint_id, PipelineStage.RESOLVED)


def test_advance_pipeline_stage_missing_complaint_raises(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()

    manager = ComplaintManager(db_manager=db_manager, ai_service=_make_ai_service("{}"))
    with pytest.raises(ComplaintManagerError):
        manager.advance_pipeline_stage(999, PipelineStage.AI_TRIAGED)


# ---------------------------------------------------------------------------
# Critical-priority admin alert broadcast
# ---------------------------------------------------------------------------


def test_critical_complaint_notifies_all_admins_and_citizen(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)

    ai_service = _make_ai_service(
        '{"category": "Safety", "priority": "Critical", "summary": "Gas leak reported."}'
    )
    notification_manager = NotificationManager(db_manager=db_manager)
    manager = ComplaintManager(
        db_manager=db_manager, ai_service=ai_service, notification_manager=notification_manager
    )

    result = manager.submit_complaint(
        user_id=users["citizen_id"], description="Gas leak on Elm St", location="Elm St"
    )

    assert result["is_critical"] is True

    admin_notifications = notification_manager.get_notifications_for_user(users["admin_id"])
    super_admin_notifications = notification_manager.get_notifications_for_user(users["super_admin_id"])
    citizen_notifications = notification_manager.get_notifications_for_user(users["citizen_id"])

    assert any("CRITICAL" in n.message for n in admin_notifications)
    assert any("CRITICAL" in n.message for n in super_admin_notifications)
    assert any("escalated" in n.message for n in citizen_notifications)


def test_non_critical_complaint_does_not_alert_admins(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)

    ai_service = _make_ai_service(
        '{"category": "Waste", "priority": "Low", "summary": "Overflowing bin."}'
    )
    notification_manager = NotificationManager(db_manager=db_manager)
    manager = ComplaintManager(
        db_manager=db_manager, ai_service=ai_service, notification_manager=notification_manager
    )

    manager.submit_complaint(user_id=users["citizen_id"], description="Overflowing bin")

    assert notification_manager.get_notifications_for_user(users["admin_id"]) == []


# ---------------------------------------------------------------------------
# API-level tests
# ---------------------------------------------------------------------------


def test_analytics_dashboard_includes_active_sla_breaches(temp_db_path):
    users = _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service("{}"))

    res = client.get("/api/analytics/dashboard", headers={"X-User-Id": str(users["admin_id"])})

    assert res.status_code == 200
    assert "active_sla_breaches" in res.json()
    assert res.json()["active_sla_breaches"] == 0


def test_stage_endpoint_valid_transition(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    complaint_id = db_manager.save_complaint(user_id=users["citizen_id"], description="Pothole")

    client = _build_client(temp_db_path, _make_ai_service("{}"))
    res = client.patch(
        f"/api/admin/complaints/{complaint_id}/stage",
        headers={"X-User-Id": str(users["admin_id"])},
        json={"stage": "ai_triaged"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["pipeline_stage"] == "ai_triaged"
    assert body["notified_user_id"] == users["citizen_id"]


def test_stage_endpoint_rejects_invalid_skip(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    complaint_id = db_manager.save_complaint(user_id=users["citizen_id"], description="Pothole")

    client = _build_client(temp_db_path, _make_ai_service("{}"))
    res = client.patch(
        f"/api/admin/complaints/{complaint_id}/stage",
        headers={"X-User-Id": str(users["admin_id"])},
        json={"stage": "dispatched"},
    )

    assert res.status_code == 400


def test_stage_endpoint_requires_admin(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    complaint_id = db_manager.save_complaint(user_id=users["citizen_id"], description="Pothole")

    client = _build_client(temp_db_path, _make_ai_service("{}"))
    res = client.patch(
        f"/api/admin/complaints/{complaint_id}/stage",
        headers={"X-User-Id": str(users["citizen_id"])},
        json={"stage": "ai_triaged"},
    )

    assert res.status_code == 403


def test_admin_complaints_endpoint_returns_sla_fields(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    db_manager.save_complaint(user_id=users["citizen_id"], description="Pothole")

    client = _build_client(temp_db_path, _make_ai_service("{}"))
    res = client.get("/api/admin/complaints", headers={"X-User-Id": str(users["admin_id"])})

    assert res.status_code == 200
    body = res.json()[0]
    assert body["pipeline_stage"] == "submitted"
    assert body["sla_status"] == "on_time"
    assert "sla_due_date" in body
