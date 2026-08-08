"""Offline tests for Phase 2 domain/service foundations.

No Gemini API, network access, or real API key is required. Where a real
database is needed (ComplaintManager integration), a temporary SQLite file
is used and removed afterward; everywhere else DatabaseManager is mocked.
"""

import os
import sqlite3
import tempfile
from unittest.mock import MagicMock

import pytest

from app.models.ai_analysis import ComplaintCategory, ComplaintPriority
from app.models.complaint import Complaint, ComplaintStatus
from app.models.department import Department
from app.models.user import User, UserRole
from app.services.ai_service import AIAnalyzer
from app.services.analytics_service import AnalyticsService
from app.services.complaint_manager import ComplaintManager
from app.services.db_manager import (
    UNANALYZED_LABEL,
    UNASSIGNED_DEPARTMENT_LABEL,
    DatabaseError,
    DatabaseManager,
)
from app.services.notification_manager import NotificationManager, NotificationManagerError


def _new_temp_db_path(name: str) -> str:
    path = os.path.join(tempfile.gettempdir(), name)
    if os.path.exists(path):
        os.remove(path)
    return path


def _seed_user(db_path: str, email: str = "seed@example.com") -> int:
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("INSERT INTO users (name, email) VALUES ('Seed User', ?)", (email,))
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return user_id


# ---------------------------------------------------------------------------
# 1. Complaint object creation
# ---------------------------------------------------------------------------


def test_complaint_creation_defaults():
    complaint = Complaint(user_id=1, description="Broken streetlight")

    assert complaint.status == ComplaintStatus.OPEN
    assert complaint.department_id is None
    assert complaint.location is None
    assert complaint.id is None


def test_complaint_creation_with_all_fields():
    complaint = Complaint(
        user_id=1,
        description="Pothole",
        department_id=5,
        location="Main St",
        status=ComplaintStatus.ASSIGNED,
    )

    assert complaint.department_id == 5
    assert complaint.location == "Main St"
    assert complaint.status == ComplaintStatus.ASSIGNED


def test_user_is_admin():
    citizen = User(name="A", email="a@example.com")
    admin = User(name="B", email="b@example.com", role=UserRole.ADMIN)

    assert citizen.is_admin() is False
    assert admin.is_admin() is True


# ---------------------------------------------------------------------------
# 2. Department mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "category,expected_name",
    [
        (ComplaintCategory.ROAD, "Road Maintenance"),
        (ComplaintCategory.WATER, "Water & Sewerage"),
        (ComplaintCategory.WASTE, "Waste Management"),
        (ComplaintCategory.ELECTRICITY, "Electricity"),
        (ComplaintCategory.DRAINAGE, "Drainage"),
        (ComplaintCategory.SAFETY, "Public Safety"),
        (ComplaintCategory.OTHER, "General Services"),
    ],
)
def test_department_name_for_category(category, expected_name):
    assert Department.name_for_category(category) == expected_name


# ---------------------------------------------------------------------------
# 3. Complaint status transition
# ---------------------------------------------------------------------------


def test_complaint_update_status_valid_transition():
    complaint = Complaint(user_id=1, description="Leak")

    complaint.update_status(ComplaintStatus.ASSIGNED)
    assert complaint.status == ComplaintStatus.ASSIGNED

    complaint.update_status(ComplaintStatus.RESOLVED)
    assert complaint.status == ComplaintStatus.RESOLVED
    assert complaint.is_closed() is True


def test_complaint_update_status_rejects_non_enum_value():
    complaint = Complaint(user_id=1, description="Leak")

    with pytest.raises(ValueError):
        complaint.update_status("resolved")


def test_complaint_status_rejects_unknown_raw_value():
    with pytest.raises(ValueError):
        ComplaintStatus("archived")


# ---------------------------------------------------------------------------
# 4. Notification creation
# ---------------------------------------------------------------------------


def test_notification_manager_notify_creates_notification():
    db_manager = MagicMock()
    db_manager.save_notification.return_value = 42

    manager = NotificationManager(db_manager=db_manager)
    notification = manager.notify(user_id=1, message="Your complaint was assigned.", complaint_id=7)

    db_manager.save_notification.assert_called_once_with(
        user_id=1, message="Your complaint was assigned.", complaint_id=7
    )
    assert notification.id == 42
    assert notification.user_id == 1
    assert notification.complaint_id == 7
    assert notification.message == "Your complaint was assigned."
    assert notification.is_read is False


def test_notification_manager_notify_rejects_empty_message():
    db_manager = MagicMock()
    manager = NotificationManager(db_manager=db_manager)

    with pytest.raises(NotificationManagerError):
        manager.notify(user_id=1, message="   ")

    db_manager.save_notification.assert_not_called()


def test_notification_manager_get_notifications_for_user():
    db_manager = MagicMock()
    db_manager.get_notifications_for_user.return_value = [
        (1, 10, 7, "Complaint assigned", 0, "2026-08-08 10:00:00"),
        (2, 10, None, "Welcome", 1, "2026-08-07 09:00:00"),
    ]

    manager = NotificationManager(db_manager=db_manager)
    notifications = manager.get_notifications_for_user(user_id=10)

    assert len(notifications) == 2
    assert notifications[0].id == 1
    assert notifications[0].complaint_id == 7
    assert notifications[0].is_read is False
    assert notifications[1].complaint_id is None
    assert notifications[1].is_read is True


# ---------------------------------------------------------------------------
# 5. Analytics calculations
# ---------------------------------------------------------------------------


def test_analytics_service_total_complaints():
    db_manager = MagicMock()
    db_manager.count_total_complaints.return_value = 15

    service = AnalyticsService(db_manager=db_manager)

    assert service.total_complaints() == 15


def test_analytics_service_complaints_by_category_fills_missing_with_zero():
    db_manager = MagicMock()
    db_manager.count_complaints_by_category.return_value = {"Road": 3, "Water": 1}

    service = AnalyticsService(db_manager=db_manager)
    result = service.complaints_by_category()

    assert result["Road"] == 3
    assert result["Water"] == 1
    assert result["Waste"] == 0
    assert result["Safety"] == 0
    assert result[UNANALYZED_LABEL] == 0
    assert set(result.keys()) == {c.value for c in ComplaintCategory} | {UNANALYZED_LABEL}


def test_analytics_service_complaints_by_category_includes_unanalyzed_bucket():
    db_manager = MagicMock()
    db_manager.count_complaints_by_category.return_value = {"Road": 3, UNANALYZED_LABEL: 2}

    service = AnalyticsService(db_manager=db_manager)
    result = service.complaints_by_category()

    assert result[UNANALYZED_LABEL] == 2


def test_analytics_service_complaints_by_priority_fills_missing_with_zero():
    db_manager = MagicMock()
    db_manager.count_complaints_by_priority.return_value = {"High": 2}

    service = AnalyticsService(db_manager=db_manager)
    result = service.complaints_by_priority()

    assert result["High"] == 2
    assert result["Low"] == 0
    assert result["Critical"] == 0
    assert result[UNANALYZED_LABEL] == 0
    assert set(result.keys()) == {p.value for p in ComplaintPriority} | {UNANALYZED_LABEL}


def test_analytics_service_complaints_by_status_fills_missing_with_zero():
    db_manager = MagicMock()
    db_manager.count_complaints_by_status.return_value = {"open": 4}

    service = AnalyticsService(db_manager=db_manager)
    result = service.complaints_by_status()

    assert result["open"] == 4
    assert result["assigned"] == 0
    assert result["closed"] == 0
    assert set(result.keys()) == {s.value for s in ComplaintStatus}


def test_analytics_service_complaints_by_department_passthrough():
    db_manager = MagicMock()
    db_manager.count_complaints_by_department.return_value = {"Road Maintenance": 5}

    service = AnalyticsService(db_manager=db_manager)
    result = service.complaints_by_department()

    assert result == {"Road Maintenance": 5, UNASSIGNED_DEPARTMENT_LABEL: 0}


def test_analytics_service_complaints_by_department_includes_unassigned_count():
    db_manager = MagicMock()
    db_manager.count_complaints_by_department.return_value = {
        "Road Maintenance": 5,
        UNASSIGNED_DEPARTMENT_LABEL: 3,
    }

    service = AnalyticsService(db_manager=db_manager)
    result = service.complaints_by_department()

    assert result[UNASSIGNED_DEPARTMENT_LABEL] == 3


# ---------------------------------------------------------------------------
# 6. ComplaintManager: deterministic department assignment (integration)
#    plus a re-check that Phase 1 AI behavior is untouched.
# ---------------------------------------------------------------------------


def test_complaint_manager_assigns_department_deterministically():
    db_path = os.path.join(tempfile.gettempdir(), "phase2_complaint_manager_test.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()

    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO users (name, email) VALUES ('Test User', 'phase2@example.com')")
    conn.commit()
    conn.close()

    ai_client = MagicMock()
    ai_response = MagicMock()
    ai_response.text = (
        '{"category": "Water", "priority": "High", '
        '"summary": "Burst pipe flooding the street."}'
    )
    ai_client.models.generate_content.return_value = ai_response
    ai_service = AIAnalyzer(client=ai_client)

    manager = ComplaintManager(db_manager=db_manager, ai_service=ai_service)

    try:
        result = manager.submit_complaint(
            user_id=1, description="Burst pipe on Elm St", location="Elm St"
        )

        assert result["category"] == "Water"
        assert result["ai_status"] == "success"
        assert result["department_id"] is not None

        conn = sqlite3.connect(db_path)
        department_row = conn.execute(
            "SELECT name, category FROM departments WHERE id = ?",
            (result["department_id"],),
        ).fetchone()
        complaint_row = conn.execute(
            "SELECT department_id, location FROM complaints WHERE id = ?",
            (result["complaint_id"],),
        ).fetchone()
        conn.close()

        assert department_row == ("Water & Sewerage", "Water")
        assert complaint_row == (result["department_id"], "Elm St")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_complaint_manager_respects_explicit_department_id():
    db_path = os.path.join(tempfile.gettempdir(), "phase2_explicit_department_test.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()

    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO users (name, email) VALUES ('Test User', 'phase2b@example.com')")
    conn.execute(
        "INSERT INTO departments (name, category) VALUES ('Custom Dept', 'Other')"
    )
    conn.commit()
    explicit_department_id = conn.execute(
        "SELECT id FROM departments WHERE name = 'Custom Dept'"
    ).fetchone()[0]
    conn.close()

    ai_service = AIAnalyzer(client=MagicMock(**{"models.generate_content.side_effect": ConnectionError("down")}))
    manager = ComplaintManager(db_manager=db_manager, ai_service=ai_service)

    try:
        result = manager.submit_complaint(
            user_id=1,
            description="Some complaint",
            department_id=explicit_department_id,
        )
        assert result["department_id"] == explicit_department_id
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


# ---------------------------------------------------------------------------
# Phase 2 fixes: real-SQLite coverage for previously mocked-only paths,
# and regression tests for the audit findings.
# ---------------------------------------------------------------------------


def test_db_manager_save_and_get_notifications_real_db():
    db_path = _new_temp_db_path("phase2_fix_notifications_real_db.db")
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()
    user_id = _seed_user(db_path, email="notif_real@example.com")

    try:
        notification_id = db_manager.save_notification(
            user_id=user_id, message="Complaint received", complaint_id=None
        )
        assert notification_id is not None

        rows = db_manager.get_notifications_for_user(user_id)
        assert len(rows) == 1
        row = rows[0]
        assert row[0] == notification_id
        assert row[1] == user_id
        assert row[2] is None
        assert row[3] == "Complaint received"
        assert row[4] == 0
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_db_manager_count_methods_real_db():
    db_path = _new_temp_db_path("phase2_fix_count_methods_real_db.db")
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()
    user_id = _seed_user(db_path, email="counts_real@example.com")

    ai_client = MagicMock()
    ai_response = MagicMock()
    ai_response.text = '{"category": "Road", "priority": "High", "summary": "Pothole."}'
    ai_client.models.generate_content.return_value = ai_response
    ai_service = AIAnalyzer(client=ai_client)
    manager = ComplaintManager(db_manager=db_manager, ai_service=ai_service)

    try:
        result = manager.submit_complaint(user_id=user_id, description="Pothole on 5th")

        assert db_manager.count_total_complaints() == 1
        assert db_manager.count_complaints_by_category() == {"Road": 1}
        assert db_manager.count_complaints_by_priority() == {"High": 1}
        assert db_manager.count_complaints_by_status() == {"open": 1}
        assert db_manager.count_complaints_by_department() == {"Road Maintenance": 1}
        assert result["department_id"] is not None
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_complaint_manager_ai_failure_with_automatic_department_assignment():
    db_path = _new_temp_db_path("phase2_fix_ai_fail_auto_dept.db")
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()
    user_id = _seed_user(db_path, email="ai_fail_auto_dept@example.com")

    ai_service = AIAnalyzer(
        client=MagicMock(**{"models.generate_content.side_effect": ConnectionError("down")})
    )
    manager = ComplaintManager(db_manager=db_manager, ai_service=ai_service)

    try:
        result = manager.submit_complaint(user_id=user_id, description="Something broke")

        assert result["ai_status"] == "failed"
        assert result["category"] == "Other"
        assert result["priority"] == "Medium"
        assert result["department_id"] is not None

        conn = sqlite3.connect(db_path)
        ai_row = conn.execute(
            "SELECT category, priority, summary, ai_status FROM ai_analysis "
            "WHERE complaint_id = ?",
            (result["complaint_id"],),
        ).fetchone()
        department_row = conn.execute(
            "SELECT name, category FROM departments WHERE id = ?",
            (result["department_id"],),
        ).fetchone()
        conn.close()

        assert ai_row == (
            "Other",
            "Medium",
            "AI analysis unavailable. Manual review required.",
            "failed",
        )
        assert department_row == ("General Services", "Other")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


class _DepartmentAssignmentFailingDatabaseManager(DatabaseManager):
    # Simulates a DatabaseManager-level failure isolated to department assignment.
    def get_or_create_department(self, name: str, category: ComplaintCategory) -> int:
        raise DatabaseError("Simulated department assignment failure")


def test_complaint_manager_department_assignment_failure_preserves_ai_analysis():
    db_path = _new_temp_db_path("phase2_fix_dept_failure_preserves_ai.db")
    db_manager = _DepartmentAssignmentFailingDatabaseManager(db_path=db_path)
    db_manager.initialize_database()
    user_id = _seed_user(db_path, email="dept_fail@example.com")

    ai_client = MagicMock()
    ai_response = MagicMock()
    ai_response.text = '{"category": "Road", "priority": "Critical", "summary": "Sinkhole."}'
    ai_client.models.generate_content.return_value = ai_response
    ai_service = AIAnalyzer(client=ai_client)
    manager = ComplaintManager(db_manager=db_manager, ai_service=ai_service)

    try:
        result = manager.submit_complaint(user_id=user_id, description="Sinkhole on Elm St")

        assert result["ai_status"] == "success"
        assert result["category"] == "Road"
        assert result["department_id"] is None

        conn = sqlite3.connect(db_path)
        complaint_row = conn.execute(
            "SELECT department_id FROM complaints WHERE id = ?", (result["complaint_id"],)
        ).fetchone()
        ai_row = conn.execute(
            "SELECT category, priority, ai_status FROM ai_analysis WHERE complaint_id = ?",
            (result["complaint_id"],),
        ).fetchone()
        conn.close()

        assert complaint_row == (None,)
        assert ai_row == ("Road", "Critical", "success")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_db_manager_update_complaint_department_missing_id_raises():
    db_path = _new_temp_db_path("phase2_fix_missing_complaint_dept_update.db")
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()
    department_id = db_manager.get_or_create_department(
        "General Services", ComplaintCategory.OTHER
    )

    try:
        with pytest.raises(DatabaseError):
            db_manager.update_complaint_department(
                complaint_id=999999, department_id=department_id
            )
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_db_manager_count_complaints_by_department_includes_unassigned_bucket():
    db_path = _new_temp_db_path("phase2_fix_unassigned_department_bucket.db")
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()
    user_id = _seed_user(db_path, email="unassigned_dept@example.com")

    try:
        db_manager.save_complaint(user_id=user_id, description="No department yet")
        counts = db_manager.count_complaints_by_department()
        assert counts == {UNASSIGNED_DEPARTMENT_LABEL: 1}
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_db_manager_count_complaints_by_category_and_priority_include_unanalyzed_bucket():
    db_path = _new_temp_db_path("phase2_fix_unanalyzed_bucket.db")
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()
    user_id = _seed_user(db_path, email="unanalyzed@example.com")

    try:
        db_manager.save_complaint(user_id=user_id, description="No AI analysis yet")
        assert db_manager.count_complaints_by_category() == {UNANALYZED_LABEL: 1}
        assert db_manager.count_complaints_by_priority() == {UNANALYZED_LABEL: 1}
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_db_manager_get_or_create_department_idempotent():
    db_path = _new_temp_db_path("phase2_fix_get_or_create_department_idempotent.db")
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()

    try:
        first_id = db_manager.get_or_create_department("Public Safety", ComplaintCategory.SAFETY)
        second_id = db_manager.get_or_create_department(
            "Public Safety", ComplaintCategory.SAFETY
        )
        assert first_id == second_id

        conn = sqlite3.connect(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM departments WHERE name = 'Public Safety'"
        ).fetchone()[0]
        conn.close()
        assert count == 1
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_db_manager_update_complaint_status_persists():
    db_path = _new_temp_db_path("phase2_fix_status_persist.db")
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()
    user_id = _seed_user(db_path, email="status_persist@example.com")

    try:
        complaint_id = db_manager.save_complaint(
            user_id=user_id, description="Needs a status change"
        )

        db_manager.update_complaint_status(complaint_id, ComplaintStatus.ASSIGNED)
        conn = sqlite3.connect(db_path)
        status = conn.execute(
            "SELECT status FROM complaints WHERE id = ?", (complaint_id,)
        ).fetchone()[0]
        conn.close()
        assert status == "assigned"

        db_manager.update_complaint_status(complaint_id, ComplaintStatus.RESOLVED)
        conn = sqlite3.connect(db_path)
        status = conn.execute(
            "SELECT status FROM complaints WHERE id = ?", (complaint_id,)
        ).fetchone()[0]
        conn.close()
        assert status == "resolved"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_db_manager_update_complaint_status_missing_id_raises():
    db_path = _new_temp_db_path("phase2_fix_status_missing_id.db")
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()

    try:
        with pytest.raises(DatabaseError):
            db_manager.update_complaint_status(999999, ComplaintStatus.CLOSED)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_db_manager_update_complaint_status_rejects_non_enum_value():
    db_path = _new_temp_db_path("phase2_fix_status_invalid_type.db")
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()
    user_id = _seed_user(db_path, email="status_invalid@example.com")

    try:
        complaint_id = db_manager.save_complaint(user_id=user_id, description="x")
        with pytest.raises(DatabaseError):
            db_manager.update_complaint_status(complaint_id, "resolved")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
