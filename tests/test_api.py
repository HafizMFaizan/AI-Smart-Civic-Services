"""API-level tests for the Phase 3 FastAPI application.

Each test builds an isolated app via create_app() pointed at a fresh
temporary SQLite file and a mocked Gemini client -- no real network access,
API key, or shared state between tests.
"""

import os
import sqlite3
import tempfile
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.ai_analysis import ComplaintCategory
from app.services.ai_service import AIAnalyzer
from app.services.db_manager import (
    UNANALYZED_LABEL,
    UNASSIGNED_DEPARTMENT_LABEL,
    DatabaseManager,
)


def _make_ai_service(response_text: str = None, raise_exception: Exception = None) -> AIAnalyzer:
    client = MagicMock()
    if raise_exception is not None:
        client.models.generate_content.side_effect = raise_exception
    else:
        response = MagicMock()
        response.text = response_text
        client.models.generate_content.return_value = response
    return AIAnalyzer(client=client)


@pytest.fixture
def temp_db_path():
    path = os.path.join(tempfile.gettempdir(), f"phase3_api_test_{uuid.uuid4().hex}.db")
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
        "INSERT INTO users (name, email, role) VALUES ('Admin One', 'admin1@example.com', 'admin')"
    ).lastrowid
    conn.commit()
    conn.close()
    return {"citizen_id": citizen_id, "admin_id": admin_id}


def _build_client(db_path: str, ai_service: AIAnalyzer) -> TestClient:
    db_manager = DatabaseManager(db_path=db_path)
    app = create_app(db_manager=db_manager, ai_service=ai_service)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Health endpoint
# ---------------------------------------------------------------------------


def test_health_endpoint(temp_db_path):
    _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# 2 & 3. Citizen complaint submission + AI success
# ---------------------------------------------------------------------------


def test_submit_complaint_ai_success(temp_db_path):
    users = _seed_users(temp_db_path)
    ai_service = _make_ai_service(
        response_text='{"category": "Road", "priority": "High", "summary": "Pothole on Main St."}'
    )
    client = _build_client(temp_db_path, ai_service)

    response = client.post(
        "/api/complaints",
        json={
            "user_id": users["citizen_id"],
            "description": "Large pothole",
            "location": "Main St",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["ai_status"] == "success"
    assert body["category"] == "Road"
    assert body["priority"] == "High"
    assert body["department_id"] is not None
    assert isinstance(body["complaint_id"], int)


# ---------------------------------------------------------------------------
# 4. AI failure / fallback
# ---------------------------------------------------------------------------


def test_submit_complaint_ai_failure_fallback(temp_db_path):
    users = _seed_users(temp_db_path)
    ai_service = _make_ai_service(raise_exception=ConnectionError("down"))
    client = _build_client(temp_db_path, ai_service)

    response = client.post(
        "/api/complaints",
        json={"user_id": users["citizen_id"], "description": "Something is broken"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["ai_status"] == "failed"
    assert body["category"] == "Other"
    assert body["priority"] == "Medium"
    assert body["department_id"] is not None


# ---------------------------------------------------------------------------
# 5. Notification retrieval
# ---------------------------------------------------------------------------


def test_get_citizen_notifications(temp_db_path):
    users = _seed_users(temp_db_path)
    ai_service = _make_ai_service(raise_exception=ConnectionError("down"))
    client = _build_client(temp_db_path, ai_service)

    submit_response = client.post(
        "/api/complaints",
        json={"user_id": users["citizen_id"], "description": "Broken streetlight"},
    )
    complaint_id = submit_response.json()["complaint_id"]

    client.patch(
        f"/api/admin/complaints/{complaint_id}/status",
        json={"status": "assigned"},
        headers={"X-User-Id": str(users["admin_id"])},
    )

    response = client.get(f"/api/citizens/{users['citizen_id']}/notifications")

    assert response.status_code == 200
    notifications = response.json()
    assert len(notifications) == 1
    assert notifications[0]["complaint_id"] == complaint_id
    assert "assigned" in notifications[0]["message"]


def test_get_citizen_complaints(temp_db_path):
    users = _seed_users(temp_db_path)
    ai_service = _make_ai_service(
        response_text='{"category": "Waste", "priority": "Low", "summary": "Overflowing bin."}'
    )
    client = _build_client(temp_db_path, ai_service)

    client.post(
        "/api/complaints",
        json={"user_id": users["citizen_id"], "description": "Overflowing trash bin"},
    )

    response = client.get(f"/api/citizens/{users['citizen_id']}/complaints")

    assert response.status_code == 200
    complaints = response.json()
    assert len(complaints) == 1
    assert complaints[0]["category"] == "Waste"
    assert complaints[0]["assigned_department"] == "Waste Management"


# ---------------------------------------------------------------------------
# 6 & 7. Admin status update + notification after status update
# ---------------------------------------------------------------------------


def test_admin_status_update_notifies_citizen(temp_db_path):
    users = _seed_users(temp_db_path)
    ai_service = _make_ai_service(
        response_text='{"category": "Water", "priority": "Low", "summary": "Minor leak."}'
    )
    client = _build_client(temp_db_path, ai_service)

    submit_response = client.post(
        "/api/complaints",
        json={"user_id": users["citizen_id"], "description": "Small leak"},
    )
    complaint_id = submit_response.json()["complaint_id"]

    response = client.patch(
        f"/api/admin/complaints/{complaint_id}/status",
        json={"status": "resolved"},
        headers={"X-User-Id": str(users["admin_id"])},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["notified_user_id"] == users["citizen_id"]

    notifications = client.get(f"/api/citizens/{users['citizen_id']}/notifications").json()
    assert any(n["complaint_id"] == complaint_id for n in notifications)


# ---------------------------------------------------------------------------
# 8, 9, 10. Analytics endpoint + Unassigned + Unanalyzed buckets
# ---------------------------------------------------------------------------


def test_analytics_dashboard_includes_unassigned_and_unanalyzed_buckets(temp_db_path):
    users = _seed_users(temp_db_path)
    # Insert a complaint with no ai_analysis/department directly, to exercise
    # the "Unanalyzed"/"Unassigned" buckets without depending on AI failure
    # behavior (which always produces a fallback ai_analysis row).
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    db_manager.save_complaint(user_id=users["citizen_id"], description="No analysis yet")

    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.get(
        "/api/analytics/dashboard", headers={"X-User-Id": str(users["admin_id"])}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_complaints"] == 1
    assert body["by_category"][UNANALYZED_LABEL] == 1
    assert body["by_priority"][UNANALYZED_LABEL] == 1
    assert body["by_department"][UNASSIGNED_DEPARTMENT_LABEL] == 1


def test_analytics_dashboard_reflects_successful_complaint(temp_db_path):
    users = _seed_users(temp_db_path)
    ai_service = _make_ai_service(
        response_text='{"category": "Safety", "priority": "Critical", "summary": "Exposed wiring."}'
    )
    client = _build_client(temp_db_path, ai_service)

    client.post(
        "/api/complaints",
        json={"user_id": users["citizen_id"], "description": "Exposed wiring near playground"},
    )

    body = client.get(
        "/api/analytics/dashboard", headers={"X-User-Id": str(users["admin_id"])}
    ).json()

    assert body["total_complaints"] == 1
    assert body["by_category"]["Safety"] == 1
    assert body["by_priority"]["Critical"] == 1
    assert body["by_department"]["Public Safety"] == 1


# ---------------------------------------------------------------------------
# Hardening pass: analytics admin gating
# ---------------------------------------------------------------------------


def test_analytics_dashboard_rejects_missing_header(temp_db_path):
    _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.get("/api/analytics/dashboard")

    assert response.status_code == 401


def test_analytics_dashboard_rejects_citizen_role(temp_db_path):
    users = _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.get(
        "/api/analytics/dashboard", headers={"X-User-Id": str(users["citizen_id"])}
    )

    assert response.status_code == 403


def test_analytics_dashboard_allows_admin_role(temp_db_path):
    users = _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.get(
        "/api/analytics/dashboard", headers={"X-User-Id": str(users["admin_id"])}
    )

    assert response.status_code == 200
    assert response.json()["total_complaints"] == 0


# ---------------------------------------------------------------------------
# Hardening pass: invalid department_id on complaint submission
# ---------------------------------------------------------------------------


def test_submit_complaint_with_invalid_department_id_returns_4xx(temp_db_path):
    users = _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.post(
        "/api/complaints",
        json={
            "user_id": users["citizen_id"],
            "description": "Pothole near the park",
            "department_id": 999999,
        },
    )

    assert 400 <= response.status_code < 500
    assert response.status_code != 500


def test_submit_complaint_with_valid_explicit_department_id_still_succeeds(temp_db_path):
    users = _seed_users(temp_db_path)
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    department_id = db_manager.get_or_create_department("Custom Dept", ComplaintCategory.OTHER)

    ai_service = _make_ai_service(raise_exception=ConnectionError("down"))
    client = _build_client(temp_db_path, ai_service)

    response = client.post(
        "/api/complaints",
        json={
            "user_id": users["citizen_id"],
            "description": "Test with explicit valid department",
            "department_id": department_id,
        },
    )

    assert response.status_code == 201
    assert response.json()["department_id"] == department_id


def test_submit_complaint_without_department_id_still_succeeds(temp_db_path):
    users = _seed_users(temp_db_path)
    ai_service = _make_ai_service(
        response_text='{"category": "Road", "priority": "Medium", "summary": "Crack in sidewalk."}'
    )
    client = _build_client(temp_db_path, ai_service)

    response = client.post(
        "/api/complaints",
        json={"user_id": users["citizen_id"], "description": "Crack in sidewalk"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["ai_status"] == "success"
    assert body["category"] == "Road"
    assert body["department_id"] is not None


# ---------------------------------------------------------------------------
# 11. Invalid request handling
# ---------------------------------------------------------------------------


def test_submit_complaint_missing_required_field_returns_422(temp_db_path):
    _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.post("/api/complaints", json={"description": "Missing user_id"})

    assert response.status_code == 422


def test_admin_status_update_invalid_status_returns_422(temp_db_path):
    users = _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.patch(
        "/api/admin/complaints/1/status",
        json={"status": "not-a-real-status"},
        headers={"X-User-Id": str(users["admin_id"])},
    )

    assert response.status_code == 422


def test_admin_status_update_missing_complaint_returns_404(temp_db_path):
    users = _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.patch(
        "/api/admin/complaints/999999/status",
        json={"status": "resolved"},
        headers={"X-User-Id": str(users["admin_id"])},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 12. Admin authorization / role behavior
# ---------------------------------------------------------------------------


def test_admin_endpoint_rejects_missing_header(temp_db_path):
    _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.get("/api/admin/complaints")

    assert response.status_code == 401


def test_admin_endpoint_rejects_citizen_role(temp_db_path):
    users = _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.get(
        "/api/admin/complaints", headers={"X-User-Id": str(users["citizen_id"])}
    )

    assert response.status_code == 403


def test_admin_endpoint_rejects_unknown_user(temp_db_path):
    _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.get("/api/admin/complaints", headers={"X-User-Id": "999999"})

    assert response.status_code == 403


def test_admin_endpoint_allows_admin_role(temp_db_path):
    users = _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.get(
        "/api/admin/complaints", headers={"X-User-Id": str(users["admin_id"])}
    )

    assert response.status_code == 200
    assert response.json() == []
