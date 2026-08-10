"""Tests for the salted-password migration and granular admin permission
enforcement added after a security review of the auth layer:

- Passwords are now stored as salted PBKDF2-HMAC-SHA256, not plain SHA-256.
- Pre-migration (legacy) plain-SHA-256 hashes still authenticate once, and
  are transparently upgraded to the new format on that successful login.
- Admin-gated endpoints now check the specific permission
  ("manage_complaints" / "view_analytics") in users.permissions, not just
  the coarse admin/super_admin role -- super_admin always bypasses.
"""

import json
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
    path = os.path.join(tempfile.gettempdir(), f"security_test_{uuid.uuid4().hex}.db")
    if os.path.exists(path):
        os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def _make_ai_service() -> AIAnalyzer:
    client = MagicMock()
    response = MagicMock()
    response.text = "{}"
    client.models.generate_content.return_value = response
    return AIAnalyzer(client=client)


def _build_client(db_path: str) -> TestClient:
    db_manager = DatabaseManager(db_path=db_path)
    app = create_app(db_manager=db_manager, ai_service=_make_ai_service())
    return TestClient(app)


def _seed_user(db_path: str, role: str, permissions: list, email: str) -> int:
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_database()
    conn = sqlite3.connect(db_path)
    user_id = conn.execute(
        "INSERT INTO users (name, email, role, permissions) VALUES (?, ?, ?, ?)",
        ("Test User", email, role, json.dumps(permissions)),
    ).lastrowid
    conn.commit()
    conn.close()
    return user_id


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def test_hash_password_is_salted_pbkdf2_not_plain_sha256():
    hash1 = DatabaseManager._hash_password("same-password")
    hash2 = DatabaseManager._hash_password("same-password")

    assert hash1 != hash2  # different random salt each time
    assert hash1.startswith("pbkdf2_sha256$")
    import hashlib
    assert hash1 != hashlib.sha256("same-password".encode()).hexdigest()


def test_verify_password_accepts_correct_and_rejects_wrong():
    stored = DatabaseManager._hash_password("correct-horse")
    assert DatabaseManager._verify_password("correct-horse", stored) is True
    assert DatabaseManager._verify_password("wrong-password", stored) is False


def test_legacy_sha256_password_still_authenticates_and_is_upgraded(temp_db_path):
    import hashlib

    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    legacy_hash = hashlib.sha256("legacypass".encode("utf-8")).hexdigest()
    conn = sqlite3.connect(temp_db_path)
    user_id = conn.execute(
        "INSERT INTO users (name, email, role, password_hash) VALUES (?, ?, 'citizen', ?)",
        ("Legacy User", "legacy@example.com", legacy_hash),
    ).lastrowid
    conn.commit()
    conn.close()

    user = db_manager.authenticate_user(email="legacy@example.com", password="legacypass")
    assert user is not None
    assert user["id"] == user_id

    conn = sqlite3.connect(temp_db_path)
    upgraded_hash = conn.execute(
        "SELECT password_hash FROM users WHERE id = ?", (user_id,)
    ).fetchone()[0]
    conn.close()

    assert upgraded_hash.startswith("pbkdf2_sha256$")
    assert DatabaseManager._verify_password("legacypass", upgraded_hash) is True


def test_wrong_password_is_rejected(temp_db_path):
    db_manager = DatabaseManager(db_path=temp_db_path)
    db_manager.initialize_database()
    db_manager.register_user(name="Real User", email="real@example.com", password="rightpass")

    assert db_manager.authenticate_user(email="real@example.com", password="wrongpass") is None
    assert db_manager.authenticate_user(email="real@example.com", password="rightpass") is not None


# ---------------------------------------------------------------------------
# Granular permission enforcement
# ---------------------------------------------------------------------------


def test_admin_without_manage_complaints_permission_is_forbidden(temp_db_path):
    admin_id = _seed_user(temp_db_path, "admin", ["view_analytics"], "readonly_admin@example.com")
    client = _build_client(temp_db_path)

    res = client.get("/api/admin/complaints", headers={"X-User-Id": str(admin_id)})
    assert res.status_code == 403


def test_admin_with_manage_complaints_permission_is_allowed(temp_db_path):
    admin_id = _seed_user(temp_db_path, "admin", ["manage_complaints"], "dispatcher@example.com")
    client = _build_client(temp_db_path)

    res = client.get("/api/admin/complaints", headers={"X-User-Id": str(admin_id)})
    assert res.status_code == 200


def test_admin_without_view_analytics_permission_is_forbidden(temp_db_path):
    admin_id = _seed_user(temp_db_path, "admin", ["manage_complaints"], "dispatcher2@example.com")
    client = _build_client(temp_db_path)

    res = client.get("/api/analytics/dashboard", headers={"X-User-Id": str(admin_id)})
    assert res.status_code == 403


def test_admin_with_view_analytics_permission_is_allowed(temp_db_path):
    admin_id = _seed_user(temp_db_path, "admin", ["view_analytics"], "auditor@example.com")
    client = _build_client(temp_db_path)

    res = client.get("/api/analytics/dashboard", headers={"X-User-Id": str(admin_id)})
    assert res.status_code == 200


def test_super_admin_bypasses_granular_permission_checks(temp_db_path):
    super_admin_id = _seed_user(temp_db_path, "super_admin", [], "bare_super@example.com")
    client = _build_client(temp_db_path)

    assert client.get("/api/admin/complaints", headers={"X-User-Id": str(super_admin_id)}).status_code == 200
    assert client.get("/api/analytics/dashboard", headers={"X-User-Id": str(super_admin_id)}).status_code == 200


def test_admin_with_no_permissions_at_all_is_forbidden_from_both(temp_db_path):
    admin_id = _seed_user(temp_db_path, "admin", [], "no_perms_admin@example.com")
    client = _build_client(temp_db_path)

    assert client.get("/api/admin/complaints", headers={"X-User-Id": str(admin_id)}).status_code == 403
    assert client.get("/api/analytics/dashboard", headers={"X-User-Id": str(admin_id)}).status_code == 403


def test_citizen_is_forbidden_regardless_of_permissions_field(temp_db_path):
    citizen_id = _seed_user(
        temp_db_path, "citizen", ["manage_complaints", "view_analytics"], "sneaky_citizen@example.com"
    )
    client = _build_client(temp_db_path)

    assert client.get("/api/admin/complaints", headers={"X-User-Id": str(citizen_id)}).status_code == 403
