"""Tests for the department directory endpoint, citizen-chosen department
submission, and the citizen-facing SLA/pipeline fields used to render
day-by-day status.
"""

import os
import sqlite3
import tempfile
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.ai_service import AIAnalyzer
from app.services.db_manager import DatabaseManager


@pytest.fixture
def temp_db_path():
    path = os.path.join(tempfile.gettempdir(), f"departments_test_{uuid.uuid4().hex}.db")
    if os.path.exists(path):
        os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def _seed_citizen(db_path: str) -> int:
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()
    conn = sqlite3.connect(db_path)
    citizen_id = conn.execute(
        "INSERT INTO users (name, email, role) VALUES ('Citizen One', 'citizen1@example.com', 'citizen')"
    ).lastrowid
    conn.commit()
    conn.close()
    return citizen_id


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


def test_departments_are_seeded_on_fresh_database(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()

    rows = db_manager.get_all_departments()
    names = {row[1] for row in rows}

    assert names == {
        "Road Maintenance",
        "Water & Sewerage",
        "Waste Management",
        "Electricity",
        "Drainage",
        "Public Safety",
        "General Services",
    }


def test_department_seeding_is_idempotent(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    db_manager.initialize_database()

    rows = db_manager.get_all_departments()
    assert len(rows) == 7


def test_departments_endpoint_returns_seeded_departments(temp_db_path):
    citizen_id = _seed_citizen(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service("{}"))

    res = client.get("/api/departments")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 7
    assert all({"department_id", "name", "category"} <= set(d.keys()) for d in body)


def test_citizen_can_submit_complaint_with_explicit_department_choice(temp_db_path):
    citizen_id = _seed_citizen(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service("{}"))

    departments = client.get("/api/departments").json()
    electricity_dept = next(d for d in departments if d["name"] == "Electricity")

    res = client.post(
        "/api/complaints",
        json={
            "user_id": citizen_id,
            "description": "Streetlight sparking dangerously",
            "department_id": electricity_dept["department_id"],
        },
    )

    assert res.status_code == 201
    assert res.json()["department_id"] == electricity_dept["department_id"]


def test_citizen_complaints_listing_includes_live_sla_status(temp_db_path):
    citizen_id = _seed_citizen(temp_db_path)
    ai_service = _make_ai_service(
        '{"category": "Road", "priority": "High", "summary": "Deep pothole."}'
    )
    client = _build_client(temp_db_path, ai_service)

    client.post("/api/complaints", json={"user_id": citizen_id, "description": "Pothole"})

    body = client.get(f"/api/citizens/{citizen_id}/complaints").json()

    assert len(body) == 1
    complaint = body[0]
    assert complaint["pipeline_stage"] == "dispatched"
    assert complaint["sla_status"] == "on_time"
    assert complaint["sla_days"] == 4
    assert complaint["sla_due_date"] is not None
