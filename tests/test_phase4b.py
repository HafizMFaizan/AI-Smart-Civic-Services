"""Phase 4B tests: user registration, notification mark-as-read, the
Complaint response vocabulary alignment, and static-serving smoke checks
for the SPA restructure.

Uses FastAPI's TestClient against an isolated app built via create_app()
with a temp SQLite file and a mocked Gemini client -- no real network
access, API key, or shared state between tests.
"""

import os
import re
import sqlite3
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.ai_service import AIAnalyzer
from app.services.db_manager import DatabaseManager


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
    path = os.path.join(tempfile.gettempdir(), f"phase4b_test_{uuid.uuid4().hex}.db")
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
# User registration
# ---------------------------------------------------------------------------


def test_register_user_success(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.post(
        "/api/users",
        json={"name": "New Citizen", "email": "new@example.com", "phone": "555-1234"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "New Citizen"
    assert body["email"] == "new@example.com"
    assert body["role"] == "citizen"
    assert isinstance(body["user_id"], int)


def test_register_user_ignores_client_supplied_role(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.post(
        "/api/users",
        json={"name": "Sneaky", "email": "sneaky@example.com", "role": "admin"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "citizen"

    conn = sqlite3.connect(temp_db_path)
    stored_role = conn.execute(
        "SELECT role FROM users WHERE email = 'sneaky@example.com'"
    ).fetchone()[0]
    conn.close()
    assert stored_role == "citizen"


def test_register_user_duplicate_email_returns_409(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    first = client.post(
        "/api/users", json={"name": "First", "email": "dup@example.com"}
    )
    second = client.post(
        "/api/users", json={"name": "Second", "email": "dup@example.com"}
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_register_user_missing_field_returns_422(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.post("/api/users", json={"name": "No Email"})

    assert response.status_code == 422


def test_registered_user_can_submit_complaint_end_to_end(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    ai_service = _make_ai_service(
        response_text='{"category": "Road", "priority": "High", "summary": "Pothole."}'
    )
    client = _build_client(temp_db_path, ai_service)

    register_response = client.post(
        "/api/users", json={"name": "Real User", "email": "real@example.com"}
    )
    user_id = register_response.json()["user_id"]

    submit_response = client.post(
        "/api/complaints", json={"user_id": user_id, "description": "Pothole on Elm St"}
    )

    assert submit_response.status_code == 201
    assert submit_response.json()["category"] == "Road"


# ---------------------------------------------------------------------------
# Notification mark-as-read
# ---------------------------------------------------------------------------


def test_mark_notification_read(temp_db_path):
    users = _seed_users(temp_db_path)
    ai_service = _make_ai_service(raise_exception=ConnectionError("down"))
    client = _build_client(temp_db_path, ai_service)

    submit_response = client.post(
        "/api/complaints", json={"user_id": users["citizen_id"], "description": "Leak"}
    )
    complaint_id = submit_response.json()["complaint_id"]
    client.patch(
        f"/api/admin/complaints/{complaint_id}/status",
        json={"status": "assigned"},
        headers={"X-User-Id": str(users["admin_id"])},
    )

    notifications = client.get(f"/api/citizens/{users['citizen_id']}/notifications").json()
    notification_id = notifications[0]["id"]
    assert notifications[0]["is_read"] is False

    response = client.patch(f"/api/notifications/{notification_id}/read")

    assert response.status_code == 200
    assert response.json() == {"notification_id": notification_id, "is_read": True}

    refreshed = client.get(f"/api/citizens/{users['citizen_id']}/notifications").json()
    assert refreshed[0]["is_read"] is True


def test_mark_notification_read_missing_id_returns_404(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.patch("/api/notifications/999999/read")

    assert response.status_code == 404


def test_mark_notification_read_is_idempotent(temp_db_path):
    users = _seed_users(temp_db_path)
    ai_service = _make_ai_service(raise_exception=ConnectionError("down"))
    client = _build_client(temp_db_path, ai_service)

    submit_response = client.post(
        "/api/complaints", json={"user_id": users["citizen_id"], "description": "Leak"}
    )
    complaint_id = submit_response.json()["complaint_id"]
    client.patch(
        f"/api/admin/complaints/{complaint_id}/status",
        json={"status": "resolved"},
        headers={"X-User-Id": str(users["admin_id"])},
    )
    notification_id = client.get(
        f"/api/citizens/{users['citizen_id']}/notifications"
    ).json()[0]["id"]

    first = client.patch(f"/api/notifications/{notification_id}/read")
    second = client.patch(f"/api/notifications/{notification_id}/read")

    assert first.status_code == 200
    assert second.status_code == 200


# ---------------------------------------------------------------------------
# Complaint response vocabulary alignment
# ---------------------------------------------------------------------------


def test_citizen_complaint_response_uses_spec_vocabulary(temp_db_path):
    users = _seed_users(temp_db_path)
    ai_service = _make_ai_service(
        response_text='{"category": "Road", "priority": "High", "summary": "Pothole."}'
    )
    client = _build_client(temp_db_path, ai_service)

    client.post(
        "/api/complaints", json={"user_id": users["citizen_id"], "description": "Pothole"}
    )
    body = client.get(f"/api/citizens/{users['citizen_id']}/complaints").json()

    assert len(body) == 1
    complaint = body[0]
    assert set(complaint.keys()) == {
        "complaint_id",
        "description",
        "location",
        "status",
        "department_id",
        "assigned_department",
        "category",
        "priority",
        "ai_summary",
        "ai_status",
        "date",
    }
    assert complaint["assigned_department"] == "Road Maintenance"
    assert complaint["ai_summary"]
    assert complaint["date"] is not None


def test_admin_complaint_response_uses_spec_vocabulary(temp_db_path):
    users = _seed_users(temp_db_path)
    ai_service = _make_ai_service(
        response_text='{"category": "Water", "priority": "Low", "summary": "Leak."}'
    )
    client = _build_client(temp_db_path, ai_service)

    client.post(
        "/api/complaints", json={"user_id": users["citizen_id"], "description": "Leak"}
    )
    body = client.get(
        "/api/admin/complaints", headers={"X-User-Id": str(users["admin_id"])}
    ).json()

    assert len(body) == 1
    complaint = body[0]
    assert "assigned_department" in complaint
    assert "ai_summary" in complaint
    assert "date" in complaint
    assert "department_name" not in complaint
    assert "summary" not in complaint
    assert "created_at" not in complaint
    assert complaint["department_id"] is not None  # integer FK preserved, per Phase 4B decision #2


# ---------------------------------------------------------------------------
# Static file serving after the SPA restructure
# ---------------------------------------------------------------------------


def test_index_serves_spa_shell(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.get("/")

    assert response.status_code == 200
    assert "citizen-view" in response.text
    assert "admin-view" in response.text
    assert "cdn.tailwindcss.com" in response.text


def test_admin_html_redirects_into_spa(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.get("/admin.html")

    assert response.status_code == 200
    assert "#/admin" in response.text


def test_app_js_and_admin_js_declare_no_colliding_top_level_names():
    # app.js and admin.js now load into the same SPA document, sharing one
    # top-level scope. const/let collisions are a hard SyntaxError; function
    # (including async function) name collisions silently shadow instead
    # (last script loaded wins). Both classes were caught live in the
    # browser during this exact Phase 4B pass (API_BASE, loadComplaints).
    static_js_dir = Path(__file__).resolve().parent.parent / "app" / "static" / "js"
    declaration_pattern = re.compile(
        r"^(?:const|let|(?:async\s+)?function)\s+(\w+)", re.MULTILINE
    )

    app_js_names = set(declaration_pattern.findall((static_js_dir / "app.js").read_text()))
    admin_js_names = set(declaration_pattern.findall((static_js_dir / "admin.js").read_text()))

    collisions = app_js_names & admin_js_names
    assert collisions == set(), f"Colliding top-level const/let/function names: {collisions}"


def test_admin_js_escapes_assigned_department_in_complaints_table():
    # Found during the Phase 4B final audit: admin.js rendered
    # c.assigned_department directly into innerHTML without escapeHtml(),
    # inconsistent with how app.js handles the identical field. Not
    # currently exploitable (department names only ever come from the
    # fixed deterministic category mapping, never free user input), but a
    # latent XSS risk if that ever changes -- fixed for defense in depth.
    admin_js_path = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "admin.js"
    content = admin_js_path.read_text()

    assert "escapeHtml(c.assigned_department)" in content
    assert "${c.assigned_department ||" not in content
