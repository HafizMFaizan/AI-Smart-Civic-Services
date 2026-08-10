"""Phase 4A tests: admin complaint search/filtering, resolution-time
analytics, and complaint trends.

DatabaseManager-level tests use a real temporary SQLite file directly (no
mocks) for precise, fast seeding. API-level tests use FastAPI's TestClient
against an isolated app built via create_app(). No Gemini network access or
real API key is required anywhere.
"""

import os
import sqlite3
import tempfile
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.ai_analysis import AIAnalysis, AIStatus, ComplaintCategory, ComplaintPriority
from app.models.complaint import ComplaintStatus
from app.services.ai_service import AIAnalyzer
from app.services.analytics_service import AnalyticsService
from app.services.db_manager import (
    UNANALYZED_LABEL,
    DatabaseError,
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
    path = os.path.join(tempfile.gettempdir(), f"phase4a_test_{uuid.uuid4().hex}.db")
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
    conn.commit()
    conn.close()
    return {"citizen_id": citizen_id, "admin_id": admin_id}


def _build_client(db_path: str, ai_service: AIAnalyzer) -> TestClient:
    db_manager = DatabaseManager(db_path=db_path)
    app = create_app(db_manager=db_manager, ai_service=ai_service)
    return TestClient(app)


def _seed_complaint(
    db_manager: DatabaseManager,
    user_id: int,
    description: str = "A complaint",
    location: str = None,
    category: ComplaintCategory = None,
    priority: ComplaintPriority = None,
    status: ComplaintStatus = None,
) -> int:
    complaint_id = db_manager.save_complaint(
        user_id=user_id, description=description, location=location
    )
    if category is not None and priority is not None:
        db_manager.save_ai_analysis(
            AIAnalysis(
                complaint_id=complaint_id,
                category=category,
                priority=priority,
                summary="summary",
                model_name="gemini-2.5-flash",
                ai_status=AIStatus.SUCCESS,
                confidence=None,
            )
        )
    if status is not None:
        db_manager.update_complaint_status(complaint_id, status)
    return complaint_id


# ---------------------------------------------------------------------------
# Filters: DatabaseManager.get_all_complaints() -- one test per filter
# ---------------------------------------------------------------------------


def test_get_all_complaints_no_filters_matches_previous_behavior(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    _seed_complaint(db_manager, users["citizen_id"], category=ComplaintCategory.ROAD, priority=ComplaintPriority.HIGH)
    _seed_complaint(db_manager, users["citizen_id"], category=ComplaintCategory.WATER, priority=ComplaintPriority.LOW)

    rows = db_manager.get_all_complaints()

    assert len(rows) == 2


def test_filter_by_category(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    _seed_complaint(db_manager, users["citizen_id"], description="Road issue", category=ComplaintCategory.ROAD, priority=ComplaintPriority.HIGH)
    _seed_complaint(db_manager, users["citizen_id"], description="Water issue", category=ComplaintCategory.WATER, priority=ComplaintPriority.LOW)

    rows = db_manager.get_all_complaints(category="Road")

    assert len(rows) == 1
    assert rows[0][4] == "Road issue"


def test_filter_by_category_unanalyzed(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    _seed_complaint(db_manager, users["citizen_id"], description="Analyzed", category=ComplaintCategory.ROAD, priority=ComplaintPriority.HIGH)
    _seed_complaint(db_manager, users["citizen_id"], description="Not analyzed")

    rows = db_manager.get_all_complaints(category=UNANALYZED_LABEL)

    assert len(rows) == 1
    assert rows[0][4] == "Not analyzed"


def test_filter_by_priority(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    _seed_complaint(db_manager, users["citizen_id"], description="High one", category=ComplaintCategory.ROAD, priority=ComplaintPriority.HIGH)
    _seed_complaint(db_manager, users["citizen_id"], description="Low one", category=ComplaintCategory.ROAD, priority=ComplaintPriority.LOW)

    rows = db_manager.get_all_complaints(priority="High")

    assert len(rows) == 1
    assert rows[0][4] == "High one"


def test_filter_by_status(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    _seed_complaint(db_manager, users["citizen_id"], description="Open one")
    resolved_id = _seed_complaint(db_manager, users["citizen_id"], description="Resolved one", status=ComplaintStatus.RESOLVED)

    rows = db_manager.get_all_complaints(status="resolved")

    assert len(rows) == 1
    assert rows[0][0] == resolved_id


def test_filter_by_department_id(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    dept_id = db_manager.get_or_create_department("Road Maintenance", ComplaintCategory.ROAD)
    with_dept_id = db_manager.save_complaint(user_id=users["citizen_id"], description="With dept", department_id=dept_id)
    db_manager.save_complaint(user_id=users["citizen_id"], description="No dept")

    rows = db_manager.get_all_complaints(department_id=dept_id)

    assert len(rows) == 1
    assert rows[0][0] == with_dept_id


def test_filter_by_location(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    _seed_complaint(db_manager, users["citizen_id"], description="A", location="Main St")
    _seed_complaint(db_manager, users["citizen_id"], description="B", location="Elm St")

    rows = db_manager.get_all_complaints(location="Main")

    assert len(rows) == 1
    assert rows[0][5] == "Main St"


def test_filter_by_search_matches_description_or_location(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    _seed_complaint(db_manager, users["citizen_id"], description="Pothole near school", location="5th Ave")
    _seed_complaint(db_manager, users["citizen_id"], description="Water leak", location="Pothole Lane")
    _seed_complaint(db_manager, users["citizen_id"], description="Unrelated", location="Nowhere")

    rows = db_manager.get_all_complaints(search="pothole")

    assert len(rows) == 2


def test_filter_by_date_range(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    complaint_id = _seed_complaint(db_manager, users["citizen_id"], description="Dated")

    conn = sqlite3.connect(temp_db_path)
    conn.execute("UPDATE complaints SET created_at = '2026-01-15 10:00:00' WHERE id = ?", (complaint_id,))
    conn.commit()
    conn.close()

    in_range = db_manager.get_all_complaints(date_from="2026-01-01", date_to="2026-01-31")
    out_of_range = db_manager.get_all_complaints(date_from="2026-02-01", date_to="2026-02-28")

    assert len(in_range) == 1
    assert len(out_of_range) == 0


def test_combined_filters_use_and_semantics(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    _seed_complaint(db_manager, users["citizen_id"], description="Match", category=ComplaintCategory.ROAD, priority=ComplaintPriority.HIGH)
    _seed_complaint(db_manager, users["citizen_id"], description="Wrong priority", category=ComplaintCategory.ROAD, priority=ComplaintPriority.LOW)
    _seed_complaint(db_manager, users["citizen_id"], description="Wrong category", category=ComplaintCategory.WATER, priority=ComplaintPriority.HIGH)

    rows = db_manager.get_all_complaints(category="Road", priority="High")

    assert len(rows) == 1
    assert rows[0][4] == "Match"


def test_filters_with_no_matches_return_empty_list(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    _seed_complaint(db_manager, users["citizen_id"], description="Only one", category=ComplaintCategory.ROAD, priority=ComplaintPriority.HIGH)

    rows = db_manager.get_all_complaints(category="Water")

    assert rows == []


# ---------------------------------------------------------------------------
# resolved_at semantics
# ---------------------------------------------------------------------------


def test_resolved_at_set_only_on_resolved_not_closed(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    resolved_id = db_manager.save_complaint(user_id=users["citizen_id"], description="A")
    closed_id = db_manager.save_complaint(user_id=users["citizen_id"], description="B")

    db_manager.update_complaint_status(resolved_id, ComplaintStatus.RESOLVED)
    db_manager.update_complaint_status(closed_id, ComplaintStatus.CLOSED)

    conn = sqlite3.connect(temp_db_path)
    resolved_row = conn.execute("SELECT resolved_at FROM complaints WHERE id = ?", (resolved_id,)).fetchone()
    closed_row = conn.execute("SELECT resolved_at FROM complaints WHERE id = ?", (closed_id,)).fetchone()
    conn.close()

    assert resolved_row[0] is not None
    assert closed_row[0] is None


def test_resolved_at_overwritten_on_reopen_and_reresolve(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    complaint_id = db_manager.save_complaint(user_id=users["citizen_id"], description="A")

    db_manager.update_complaint_status(complaint_id, ComplaintStatus.RESOLVED)
    db_manager.update_complaint_status(complaint_id, ComplaintStatus.IN_PROGRESS)

    # Force an old resolution timestamp so the next resolve's overwrite is
    # provable regardless of real-clock second-resolution timing.
    conn = sqlite3.connect(temp_db_path)
    conn.execute(
        "UPDATE complaints SET resolved_at = '2020-01-01 00:00:00' WHERE id = ?", (complaint_id,)
    )
    conn.commit()
    conn.close()

    db_manager.update_complaint_status(complaint_id, ComplaintStatus.RESOLVED)

    conn = sqlite3.connect(temp_db_path)
    resolved_at = conn.execute(
        "SELECT resolved_at FROM complaints WHERE id = ?", (complaint_id,)
    ).fetchone()[0]
    conn.close()

    assert resolved_at is not None
    assert resolved_at != "2020-01-01 00:00:00"


# ---------------------------------------------------------------------------
# Resolution-time calculations
# ---------------------------------------------------------------------------


def test_resolution_time_stats_with_data(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    id1 = db_manager.save_complaint(user_id=users["citizen_id"], description="A")
    id2 = db_manager.save_complaint(user_id=users["citizen_id"], description="B")

    conn = sqlite3.connect(temp_db_path)
    conn.execute(
        "UPDATE complaints SET created_at = '2026-01-01 00:00:00', "
        "resolved_at = '2026-01-01 10:00:00' WHERE id = ?",
        (id1,),
    )
    conn.execute(
        "UPDATE complaints SET created_at = '2026-01-01 00:00:00', "
        "resolved_at = '2026-01-02 00:00:00' WHERE id = ?",
        (id2,),
    )
    conn.commit()
    conn.close()

    avg_hours, min_hours, max_hours, resolved_count = db_manager.get_resolution_time_stats()

    assert resolved_count == 2
    assert min_hours == pytest.approx(10.0, abs=0.01)
    assert max_hours == pytest.approx(24.0, abs=0.01)
    assert avg_hours == pytest.approx(17.0, abs=0.01)


def test_resolution_time_stats_empty_database(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()

    avg_hours, min_hours, max_hours, resolved_count = db_manager.get_resolution_time_stats()

    assert avg_hours is None
    assert min_hours is None
    assert max_hours is None
    assert resolved_count == 0


def test_analytics_service_resolution_time_stats_empty(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    service = AnalyticsService(db_manager=db_manager)

    assert service.resolution_time_stats() == {
        "average_hours": None,
        "minimum_hours": None,
        "maximum_hours": None,
        "resolved_count": 0,
    }


def test_analytics_service_resolution_time_stats_rounds_values(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    complaint_id = db_manager.save_complaint(user_id=users["citizen_id"], description="A")

    conn = sqlite3.connect(temp_db_path)
    conn.execute(
        "UPDATE complaints SET created_at = '2026-01-01 00:00:00', "
        "resolved_at = '2026-01-01 01:23:27' WHERE id = ?",
        (complaint_id,),
    )
    conn.commit()
    conn.close()

    service = AnalyticsService(db_manager=db_manager)
    stats = service.resolution_time_stats()

    assert stats["resolved_count"] == 1
    assert isinstance(stats["average_hours"], float)
    assert stats["average_hours"] == round(stats["average_hours"], 2)


# ---------------------------------------------------------------------------
# Trend calculations
# ---------------------------------------------------------------------------


def test_complaint_trends_day(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    id1 = db_manager.save_complaint(user_id=users["citizen_id"], description="A")
    id2 = db_manager.save_complaint(user_id=users["citizen_id"], description="B")
    id3 = db_manager.save_complaint(user_id=users["citizen_id"], description="C")

    conn = sqlite3.connect(temp_db_path)
    conn.execute("UPDATE complaints SET created_at = '2026-01-01 09:00:00' WHERE id = ?", (id1,))
    conn.execute("UPDATE complaints SET created_at = '2026-01-01 15:00:00' WHERE id = ?", (id2,))
    conn.execute("UPDATE complaints SET created_at = '2026-01-02 09:00:00' WHERE id = ?", (id3,))
    conn.commit()
    conn.close()

    rows = db_manager.get_complaint_trends("day")

    assert dict(rows) == {"2026-01-01": 2, "2026-01-02": 1}


def test_complaint_trends_month(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    id1 = db_manager.save_complaint(user_id=users["citizen_id"], description="A")
    id2 = db_manager.save_complaint(user_id=users["citizen_id"], description="B")

    conn = sqlite3.connect(temp_db_path)
    conn.execute("UPDATE complaints SET created_at = '2026-01-05 09:00:00' WHERE id = ?", (id1,))
    conn.execute("UPDATE complaints SET created_at = '2026-02-05 09:00:00' WHERE id = ?", (id2,))
    conn.commit()
    conn.close()

    rows = db_manager.get_complaint_trends("month")

    assert dict(rows) == {"2026-01": 1, "2026-02": 1}


def test_complaint_trends_week_returns_bucketed_counts(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    users = _seed_users(temp_db_path)
    db_manager.save_complaint(user_id=users["citizen_id"], description="A")

    rows = db_manager.get_complaint_trends("week")

    assert len(rows) == 1
    period, count = rows[0]
    assert count == 1
    assert "-W" in period


def test_complaint_trends_invalid_group_by_raises(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()

    with pytest.raises(DatabaseError):
        db_manager.get_complaint_trends("year")


def test_complaint_trends_empty_database(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()

    rows = db_manager.get_complaint_trends("day")

    assert rows == []


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------


def test_schema_migration_adds_resolved_at_without_data_loss(temp_db_path):
    # Simulate a pre-Phase-4A database (no resolved_at column) with real
    # data, then confirm initialize_database() adds the column additively
    # without touching existing rows.
    conn = sqlite3.connect(temp_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT,
            role TEXT NOT NULL DEFAULT 'citizen',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            department_id INTEGER,
            description TEXT NOT NULL,
            location TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.execute("INSERT INTO users (name, email) VALUES ('Old User', 'old@example.com')")
    conn.execute(
        "INSERT INTO complaints (user_id, description) VALUES (1, 'Pre-existing complaint')"
    )
    conn.commit()
    conn.close()

    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()

    conn = sqlite3.connect(temp_db_path)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(complaints)").fetchall()]
    preserved = conn.execute(
        "SELECT user_id, description FROM complaints WHERE description = 'Pre-existing complaint'"
    ).fetchone()
    conn.close()

    assert "resolved_at" in columns
    assert preserved == (1, "Pre-existing complaint")


# ---------------------------------------------------------------------------
# API-level: filtering, trends, resolution-time, admin authorization,
# backward compatibility, citizen listing untouched
# ---------------------------------------------------------------------------


def test_admin_complaints_filter_by_category_via_api(temp_db_path):
    users = _seed_users(temp_db_path)
    db_manager = DatabaseManager(db_path=temp_db_path)
    _seed_complaint(db_manager, users["citizen_id"], description="Road complaint", category=ComplaintCategory.ROAD, priority=ComplaintPriority.HIGH)
    _seed_complaint(db_manager, users["citizen_id"], description="Water complaint", category=ComplaintCategory.WATER, priority=ComplaintPriority.LOW)

    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))
    response = client.get(
        "/api/admin/complaints?category=Road", headers={"X-User-Id": str(users["admin_id"])}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["description"] == "Road complaint"


def test_admin_complaints_combined_filters_via_api(temp_db_path):
    users = _seed_users(temp_db_path)
    db_manager = DatabaseManager(db_path=temp_db_path)
    _seed_complaint(db_manager, users["citizen_id"], description="Match", category=ComplaintCategory.ROAD, priority=ComplaintPriority.HIGH)
    _seed_complaint(db_manager, users["citizen_id"], description="Wrong priority", category=ComplaintCategory.ROAD, priority=ComplaintPriority.LOW)

    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))
    response = client.get(
        "/api/admin/complaints?category=Road&priority=High",
        headers={"X-User-Id": str(users["admin_id"])},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["description"] == "Match"


def test_admin_complaints_filter_empty_result_via_api(temp_db_path):
    users = _seed_users(temp_db_path)
    db_manager = DatabaseManager(db_path=temp_db_path)
    _seed_complaint(db_manager, users["citizen_id"], description="Only one", category=ComplaintCategory.ROAD, priority=ComplaintPriority.HIGH)

    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))
    response = client.get(
        "/api/admin/complaints?category=Water", headers={"X-User-Id": str(users["admin_id"])}
    )

    assert response.status_code == 200
    assert response.json() == []


def test_admin_complaints_invalid_category_filter_returns_422(temp_db_path):
    users = _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.get(
        "/api/admin/complaints?category=NotACategory",
        headers={"X-User-Id": str(users["admin_id"])},
    )

    assert response.status_code == 422


def test_admin_complaints_filters_require_admin(temp_db_path):
    _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.get("/api/admin/complaints?category=Road")

    assert response.status_code == 401


def test_admin_complaints_no_filters_matches_existing_behavior_via_api(temp_db_path):
    users = _seed_users(temp_db_path)
    db_manager = DatabaseManager(db_path=temp_db_path)
    _seed_complaint(db_manager, users["citizen_id"], description="A", category=ComplaintCategory.ROAD, priority=ComplaintPriority.HIGH)
    _seed_complaint(db_manager, users["citizen_id"], description="B", category=ComplaintCategory.WATER, priority=ComplaintPriority.LOW)

    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))
    response = client.get(
        "/api/admin/complaints", headers={"X-User-Id": str(users["admin_id"])}
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_analytics_trends_endpoint(temp_db_path):
    users = _seed_users(temp_db_path)
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.save_complaint(user_id=users["citizen_id"], description="A")

    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))
    response = client.get(
        "/api/analytics/trends?group_by=day", headers={"X-User-Id": str(users["admin_id"])}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["group_by"] == "day"
    assert len(body["series"]) == 1
    assert body["series"][0]["count"] == 1


def test_analytics_trends_requires_admin(temp_db_path):
    users = _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    assert client.get("/api/analytics/trends").status_code == 401
    assert (
        client.get(
            "/api/analytics/trends", headers={"X-User-Id": str(users["citizen_id"])}
        ).status_code
        == 403
    )


def test_analytics_resolution_time_endpoint(temp_db_path):
    users = _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    response = client.get(
        "/api/analytics/resolution-time", headers={"X-User-Id": str(users["admin_id"])}
    )

    assert response.status_code == 200
    assert response.json() == {
        "average_hours": None,
        "minimum_hours": None,
        "maximum_hours": None,
        "resolved_count": 0,
    }


def test_analytics_resolution_time_requires_admin(temp_db_path):
    users = _seed_users(temp_db_path)
    client = _build_client(temp_db_path, _make_ai_service(response_text="{}"))

    assert client.get("/api/analytics/resolution-time").status_code == 401
    assert (
        client.get(
            "/api/analytics/resolution-time", headers={"X-User-Id": str(users["citizen_id"])}
        ).status_code
        == 403
    )


def test_status_update_via_api_reflects_in_resolution_time(temp_db_path):
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

    body = client.get(
        "/api/analytics/resolution-time", headers={"X-User-Id": str(users["admin_id"])}
    ).json()

    assert body["resolved_count"] == 1
    assert body["average_hours"] is not None


def test_citizen_complaint_listing_unaffected_by_phase_4a(temp_db_path):
    users = _seed_users(temp_db_path)
    ai_service = _make_ai_service(
        response_text='{"category": "Road", "priority": "High", "summary": "Pothole."}'
    )
    client = _build_client(temp_db_path, ai_service)

    client.post("/api/complaints", json={"user_id": users["citizen_id"], "description": "Pothole"})

    response = client.get(f"/api/citizens/{users['citizen_id']}/complaints")

    assert response.status_code == 200
    assert len(response.json()) == 1
