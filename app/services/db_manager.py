"""DatabaseManager: SQLite data persistence layer with RBAC, SLA management, analytics, and audit logging."""

import hashlib
import hmac
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from app.models.ai_analysis import AIAnalysis, ComplaintCategory, ComplaintPriority
from app.models.complaint import ComplaintStatus, PipelineStage
from app.models.department import CATEGORY_TO_DEPARTMENT_NAME

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = _PROJECT_ROOT / "database" / "civic_services.db"
SCHEMA_PATH = _PROJECT_ROOT / "database" / "schema.sql"

UNASSIGNED_DEPARTMENT_LABEL = "Unassigned"
UNANALYZED_LABEL = "Unanalyzed"

DEFAULT_ADMIN_NAME = "Default Admin"
DEFAULT_ADMIN_EMAIL = "admin@civicservices.local"
DEFAULT_SUPER_ADMIN_NAME = "Super Municipal Admin"
DEFAULT_SUPER_ADMIN_EMAIL = "superadmin@civicservices.local"


class DatabaseError(Exception):
    """Raised when a database operation fails."""


class DuplicateEmailError(DatabaseError):
    """Raised when creating a user with an email that is already registered."""


class DatabaseManager:
    _PBKDF2_PREFIX = "pbkdf2_sha256$"
    _PBKDF2_ITERATIONS = 260_000

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or str(DEFAULT_DB_PATH)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    def initialize_database(self) -> None:
        try:
            with self._connect() as conn:
                with open(SCHEMA_PATH, "r", encoding="utf-8") as schema_file:
                    conn.executescript(schema_file.read())
                self._migrate_schema_columns(conn)
                self._seed_default_admin(conn)
                self._seed_default_super_admin(conn)
                self._seed_default_departments(conn)
        except (sqlite3.Error, OSError) as exc:
            raise DatabaseError(f"Failed to initialize database: {exc}") from exc

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = os.urandom(16)
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, DatabaseManager._PBKDF2_ITERATIONS
        )
        return f"{DatabaseManager._PBKDF2_PREFIX}{DatabaseManager._PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        if stored_hash.startswith(DatabaseManager._PBKDF2_PREFIX):
            try:
                _, iterations_str, salt_hex, hash_hex = stored_hash.split("$")
                derived = hashlib.pbkdf2_hmac(
                    "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations_str)
                )
                return hmac.compare_digest(derived.hex(), hash_hex)
            except (ValueError, TypeError):
                return False
        # Legacy unsalted SHA-256 hash from before the salted-hash migration.
        legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy_hash, stored_hash)

    @staticmethod
    def _seed_default_admin(conn: sqlite3.Connection) -> None:
        admin_count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin'"
        ).fetchone()[0]
        if admin_count > 0:
            return

        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (DEFAULT_ADMIN_EMAIL,)
        ).fetchone()
        if existing is not None:
            return

        conn.execute(
            "INSERT INTO users (name, email, role, password_hash, permissions) VALUES (?, ?, 'admin', ?, ?)",
            (DEFAULT_ADMIN_NAME, DEFAULT_ADMIN_EMAIL, DatabaseManager._hash_password("admin123"), json.dumps(["manage_complaints", "view_analytics"])),
        )

    @staticmethod
    def _seed_default_super_admin(conn: sqlite3.Connection) -> None:
        super_count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'super_admin'"
        ).fetchone()[0]
        if super_count > 0:
            return

        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (DEFAULT_SUPER_ADMIN_EMAIL,)
        ).fetchone()
        if existing is not None:
            return

        try:
            conn.execute(
                "INSERT INTO users (name, email, role, password_hash, permissions) VALUES (?, ?, 'super_admin', ?, ?)",
                (DEFAULT_SUPER_ADMIN_NAME, DEFAULT_SUPER_ADMIN_EMAIL, DatabaseManager._hash_password("superadmin123"), json.dumps(["all"])),
            )
        except sqlite3.IntegrityError:
            conn.execute(
                "INSERT INTO users (name, email, role, password_hash, permissions) VALUES (?, ?, 'admin', ?, ?)",
                (DEFAULT_SUPER_ADMIN_NAME, DEFAULT_SUPER_ADMIN_EMAIL, DatabaseManager._hash_password("superadmin123"), json.dumps(["all"])),
            )

    @staticmethod
    def _seed_default_departments(conn: sqlite3.Connection) -> None:
        for category, name in CATEGORY_TO_DEPARTMENT_NAME.items():
            conn.execute(
                "INSERT OR IGNORE INTO departments (name, category) VALUES (?, ?)",
                (name, category.value),
            )

    @staticmethod
    def _migrate_schema_columns(conn: sqlite3.Connection) -> None:
        c_cols = [row[1] for row in conn.execute("PRAGMA table_info(complaints)").fetchall()]
        if "resolved_at" not in c_cols:
            conn.execute("ALTER TABLE complaints ADD COLUMN resolved_at TIMESTAMP")
        if "pipeline_stage" not in c_cols:
            conn.execute("ALTER TABLE complaints ADD COLUMN pipeline_stage TEXT DEFAULT 'submitted'")
        if "sla_days" not in c_cols:
            conn.execute("ALTER TABLE complaints ADD COLUMN sla_days INTEGER DEFAULT 7")
        if "sla_due_date" not in c_cols:
            conn.execute("ALTER TABLE complaints ADD COLUMN sla_due_date TIMESTAMP")
        if "sla_status" not in c_cols:
            conn.execute("ALTER TABLE complaints ADD COLUMN sla_status TEXT DEFAULT 'on_time'")
        if "department_remarks" not in c_cols:
            conn.execute("ALTER TABLE complaints ADD COLUMN department_remarks TEXT")
        if "rating_score" not in c_cols:
            conn.execute("ALTER TABLE complaints ADD COLUMN rating_score INTEGER")
        if "review_comment" not in c_cols:
            conn.execute("ALTER TABLE complaints ADD COLUMN review_comment TEXT")

        u_cols = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "password_hash" not in u_cols:
            conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT 'pbkdf2:sha256$seeded_hash_no_access'")
        if "permissions" not in u_cols:
            conn.execute("ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT '[]'")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # User Management & Auth
    def create_user(self, name: str, email: str, phone: Optional[str] = None) -> int:
        return self.register_user(name=name, email=email, password="password123", phone=phone, role="citizen")

    def register_user(
        self,
        name: str,
        email: str,
        password: str = "password123",
        phone: Optional[str] = None,
        role: str = "citizen"
    ) -> int:
        safe_role = "citizen" if role not in ("admin", "super_admin") else role
        p_hash = self._hash_password(password)
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO users (name, email, phone, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                    (name, email, phone, p_hash, safe_role),
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            if "users.email" in str(exc) or "UNIQUE" in str(exc).upper():
                raise DuplicateEmailError(f"User with email '{email}' already exists.") from exc
            raise DatabaseError(f"Failed to register user: {exc}") from exc

    def authenticate_user(self, email: str, password: str) -> Optional[Dict]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT id, name, email, phone, role, permissions, password_hash FROM users WHERE email = ?",
                    (email,),
                ).fetchone()
                if not row or not self._verify_password(password, row[6]):
                    return None

                if not row[6].startswith(self._PBKDF2_PREFIX):
                    conn.execute(
                        "UPDATE users SET password_hash = ? WHERE id = ?",
                        (self._hash_password(password), row[0]),
                    )

                return {
                    "id": row[0],
                    "name": row[1],
                    "email": row[2],
                    "phone": row[3],
                    "role": row[4],
                    "permissions": json.loads(row[5] or "[]")
                }
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to authenticate user: {exc}") from exc

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT id, name, email, phone, role, permissions FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                if not row:
                    return None
                return {
                    "id": row[0],
                    "name": row[1],
                    "email": row[2],
                    "phone": row[3],
                    "role": row[4],
                    "permissions": json.loads(row[5] or "[]")
                }
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to get user: {exc}") from exc

    def get_user_role(self, user_id: int) -> Optional[str]:
        u = self.get_user_by_id(user_id)
        return u["role"] if u else None

    def get_user_permissions(self, user_id: int) -> List[str]:
        u = self.get_user_by_id(user_id)
        return u["permissions"] if u else []

    # Admin Onboarding Applications
    def create_admin_application(self, user_id: int, department_name: str, reason: str) -> int:
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO admin_applications (user_id, department_name, reason) VALUES (?, ?, ?)",
                    (user_id, department_name, reason),
                )
                return cursor.lastrowid
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to create admin application: {exc}") from exc

    def get_pending_admin_applications(self) -> List[Dict]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT a.id, a.user_id, u.name, u.email, a.department_name, a.reason, a.status, a.created_at
                    FROM admin_applications a
                    JOIN users u ON a.user_id = u.id
                    WHERE a.status = 'pending'
                    ORDER BY a.created_at DESC
                    """
                ).fetchall()
                return [
                    {
                        "application_id": r[0],
                        "user_id": r[1],
                        "applicant_name": r[2],
                        "applicant_email": r[3],
                        "department": r[4],
                        "reason": r[5],
                        "status": r[6],
                        "created_at": str(r[7]),
                    }
                    for r in rows
                ]
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to list admin applications: {exc}") from exc

    def approve_admin_application(self, application_id: int, super_admin_id: int) -> Dict:
        try:
            with self._connect() as conn:
                app_row = conn.execute(
                    "SELECT user_id, department_name FROM admin_applications WHERE id = ? AND status = 'pending'",
                    (application_id,),
                ).fetchone()
                if not app_row:
                    raise DatabaseError("Application not found or already processed.")

                user_id, dept = app_row
                conn.execute(
                    "UPDATE users SET role = 'admin', permissions = ? WHERE id = ?",
                    (json.dumps(["manage_complaints", "view_analytics", dept]), user_id),
                )
                conn.execute(
                    "UPDATE admin_applications SET status = 'approved', approved_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (super_admin_id, application_id),
                )
                return {"application_id": application_id, "user_id": user_id, "status": "approved"}
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to approve admin application: {exc}") from exc

    # Complaints Management
    def save_complaint(
        self,
        user_id: int,
        description: str,
        department_id: Optional[int] = None,
        location: Optional[str] = None,
        sla_days: int = 7,
    ) -> int:
        due_date = (datetime.now() + timedelta(days=sla_days)).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO complaints (user_id, department_id, description, location, sla_days, sla_due_date, pipeline_stage)
                    VALUES (?, ?, ?, ?, ?, ?, 'submitted')
                    """,
                    (user_id, department_id, description, location, sla_days, due_date),
                )
                return cursor.lastrowid
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to save complaint: {exc}") from exc

    def save_ai_analysis(self, analysis: AIAnalysis) -> int:
        sla_map = {"Critical": 2, "High": 4, "Medium": 7, "Low": 14}
        sla_days = sla_map.get(analysis.priority.value, 7)
        due_date = (datetime.now() + timedelta(days=sla_days)).strftime("%Y-%m-%d %H:%M:%S")

        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO ai_analysis
                        (complaint_id, category, priority, summary, model_name, confidence, ai_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        analysis.complaint_id,
                        analysis.category.value,
                        analysis.priority.value,
                        analysis.summary,
                        analysis.model_name,
                        analysis.confidence,
                        analysis.ai_status.value,
                    ),
                )
                conn.execute(
                    """
                    UPDATE complaints
                    SET category = ?, priority = ?, pipeline_stage = 'ai_triaged', sla_days = ?, sla_due_date = ?
                    WHERE id = ?
                    """,
                    (analysis.category.value, analysis.priority.value, sla_days, due_date, analysis.complaint_id),
                )
                return cursor.lastrowid
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to save AI analysis: {exc}") from exc

    def get_complaint_owner(self, complaint_id: int) -> Optional[int]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT user_id FROM complaints WHERE id = ?", (complaint_id,)
                ).fetchone()
                return row[0] if row else None
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to get complaint owner: {exc}") from exc

    def update_complaint_pipeline_stage(self, complaint_id: int, stage: str) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE complaints SET pipeline_stage = ? WHERE id = ?", (stage, complaint_id)
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to update pipeline stage: {exc}") from exc

    def update_complaint_status(self, complaint_id: int, status: ComplaintStatus, department_remarks: Optional[str] = None) -> None:
        if not isinstance(status, ComplaintStatus):
            raise DatabaseError(f"Invalid complaint status: {status!r}")
        try:
            with self._connect() as conn:
                if status == ComplaintStatus.RESOLVED:
                    c_row = conn.execute(
                        "SELECT created_at, sla_due_date FROM complaints WHERE id = ?", (complaint_id,)
                    ).fetchone()
                    
                    sla_status = "on_time"
                    remarks = department_remarks or "Resolved within SLA window. Excellent municipal service."
                    if c_row and c_row[1]:
                        if datetime.now().strftime("%Y-%m-%d %H:%M:%S") > str(c_row[1]):
                            sla_status = "breached"
                            remarks = department_remarks or "SLA Breached - Resolution delayed beyond target deadline."

                    cursor = conn.execute(
                        """
                        UPDATE complaints
                        SET status = ?, pipeline_stage = 'resolved', resolved_at = CURRENT_TIMESTAMP,
                            sla_status = ?, department_remarks = ?
                        WHERE id = ?
                        """,
                        (status.value, sla_status, remarks, complaint_id),
                    )
                else:
                    cursor = conn.execute(
                        "UPDATE complaints SET status = ? WHERE id = ?", (status.value, complaint_id)
                    )

                if cursor.rowcount == 0:
                    raise DatabaseError(f"No complaint found with id {complaint_id}; status was not updated.")
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to update complaint status: {exc}") from exc

    def department_exists(self, department_id: int) -> bool:
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT 1 FROM departments WHERE id = ?", (department_id,)).fetchone()
                return row is not None
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to check department existence: {exc}") from exc

    def get_all_departments(self) -> List[Tuple]:
        try:
            with self._connect() as conn:
                return conn.execute(
                    "SELECT id, name, category FROM departments ORDER BY name"
                ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch departments: {exc}") from exc

    def get_or_create_department(self, name: str, category: ComplaintCategory) -> int:
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT id FROM departments WHERE name = ?", (name,)).fetchone()
                if row is not None:
                    return row[0]
                cursor = conn.execute(
                    "INSERT INTO departments (name, category) VALUES (?, ?)",
                    (name, category.value),
                )
                return cursor.lastrowid
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to get or create department: {exc}") from exc

    def update_complaint_department(self, complaint_id: int, department_id: int) -> None:
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE complaints SET department_id = ?, pipeline_stage = 'dispatched' WHERE id = ?",
                    (department_id, complaint_id),
                )
                if cursor.rowcount == 0:
                    raise DatabaseError(f"No complaint found with id {complaint_id}")
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to update complaint department: {exc}") from exc

    _EFFECTIVE_SLA_STATUS_SQL = """
        CASE
            WHEN c.status IN ('resolved', 'closed') THEN c.sla_status
            WHEN c.sla_due_date IS NOT NULL AND CURRENT_TIMESTAMP > c.sla_due_date THEN 'breached'
            ELSE 'on_time'
        END
    """

    def get_all_complaints(
        self,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        department_id: Optional[int] = None,
        location: Optional[str] = None,
        search: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        sla_status: Optional[str] = None,
    ) -> List[Tuple]:
        try:
            with self._connect() as conn:
                query = f"""
                    SELECT
                        c.id, c.user_id, u.name, u.email, c.description, c.location, c.status,
                        c.department_id, d.name AS assigned_department, a.category, a.priority,
                        a.summary AS ai_summary, a.ai_status, c.created_at,
                        c.pipeline_stage, c.sla_due_date, {self._EFFECTIVE_SLA_STATUS_SQL} AS effective_sla_status
                    FROM complaints c
                    JOIN users u ON c.user_id = u.id
                    LEFT JOIN departments d ON c.department_id = d.id
                    LEFT JOIN ai_analysis a ON c.id = a.complaint_id
                    WHERE 1=1
                """
                params: List[object] = []

                if category == UNANALYZED_LABEL:
                    query += " AND a.category IS NULL"
                elif category:
                    query += " AND a.category = ?"
                    params.append(category)

                if priority == UNANALYZED_LABEL:
                    query += " AND a.priority IS NULL"
                elif priority:
                    query += " AND a.priority = ?"
                    params.append(priority)

                if status:
                    query += " AND c.status = ?"
                    params.append(status)

                if department_id:
                    query += " AND c.department_id = ?"
                    params.append(department_id)

                if location:
                    query += " AND c.location LIKE ?"
                    params.append(f"%{location}%")

                if search:
                    query += " AND (c.description LIKE ? OR c.location LIKE ?)"
                    params.append(f"%{search}%")
                    params.append(f"%{search}%")

                if date_from:
                    query += " AND DATE(c.created_at) >= DATE(?)"
                    params.append(date_from)

                if date_to:
                    query += " AND DATE(c.created_at) <= DATE(?)"
                    params.append(date_to)

                if sla_status:
                    query += f" AND {self._EFFECTIVE_SLA_STATUS_SQL} = ?"
                    params.append(sla_status)

                query += " ORDER BY c.created_at DESC"
                return conn.execute(query, params).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch complaints: {exc}") from exc

    def get_admin_user_ids(self) -> List[int]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT id FROM users WHERE role IN ('admin', 'super_admin')"
                ).fetchall()
                return [row[0] for row in rows]
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch admin user ids: {exc}") from exc

    def count_active_sla_breaches(self) -> int:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*) FROM complaints c
                    WHERE c.status NOT IN ('resolved', 'closed')
                      AND c.sla_due_date IS NOT NULL
                      AND CURRENT_TIMESTAMP > c.sla_due_date
                    """
                ).fetchone()
                return row[0] if row else 0
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to count active SLA breaches: {exc}") from exc

    def get_complaint_pipeline_stage(self, complaint_id: int) -> Optional[str]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT pipeline_stage FROM complaints WHERE id = ?", (complaint_id,)
                ).fetchone()
                return row[0] if row else None
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch pipeline stage: {exc}") from exc

    def get_citizen_complaints(self, user_id: int) -> List[Tuple]:
        try:
            with self._connect() as conn:
                return conn.execute(
                    f"""
                    SELECT c.id, c.description, c.location, c.status, c.department_id, d.name, a.category, a.priority, a.summary, a.ai_status, c.created_at,
                           c.pipeline_stage, c.sla_days, c.sla_due_date, c.department_remarks, {self._EFFECTIVE_SLA_STATUS_SQL} AS effective_sla_status
                    FROM complaints c
                    LEFT JOIN departments d ON c.department_id = d.id
                    LEFT JOIN ai_analysis a ON c.id = a.complaint_id
                    WHERE c.user_id = ?
                    ORDER BY c.created_at DESC
                    """,
                    (user_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch citizen complaints: {exc}") from exc

    def get_complaints_for_user(self, user_id: int) -> List[Tuple]:
        return self.get_citizen_complaints(user_id)

    def get_citizen_notifications(self, user_id: int) -> List[Tuple]:
        try:
            with self._connect() as conn:
                return conn.execute(
                    """
                    SELECT id, user_id, complaint_id, message, is_read, created_at
                    FROM notifications
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    """,
                    (user_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch notifications: {exc}") from exc

    def get_notifications_for_user(self, user_id: int) -> List[Tuple]:
        return self.get_citizen_notifications(user_id)

    def save_notification(self, user_id: int, message: str, complaint_id: Optional[int] = None) -> int:
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO notifications (user_id, complaint_id, message) VALUES (?, ?, ?)",
                    (user_id, complaint_id, message),
                )
                return cursor.lastrowid
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to save notification: {exc}") from exc

    def mark_notification_read(self, notification_id: int) -> None:
        try:
            with self._connect() as conn:
                cursor = conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
                if cursor.rowcount == 0:
                    raise DatabaseError(f"No notification found with id {notification_id}")
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to mark notification as read: {exc}") from exc

    def save_sms_log(self, user_id: int, phone: str, message: str, complaint_id: Optional[int] = None) -> int:
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO sms_logs (user_id, complaint_id, phone, message) VALUES (?, ?, ?, ?)",
                    (user_id, complaint_id, phone, message),
                )
                return cursor.lastrowid
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to save SMS log: {exc}") from exc

    # Analytics Queries
    def count_total_complaints(self) -> int:
        try:
            with self._connect() as conn:
                return conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to count complaints: {exc}") from exc

    def count_complaints_by_category(self) -> Dict[str, int]:
        try:
            with self._connect() as conn:
                result = {}
                rows = conn.execute(
                    """
                    SELECT a.category, COUNT(c.id)
                    FROM complaints c
                    LEFT JOIN ai_analysis a ON c.id = a.complaint_id
                    GROUP BY a.category
                    """
                ).fetchall()
                for cat, count in rows:
                    if count > 0:
                        key = cat if cat is not None else UNANALYZED_LABEL
                        result[key] = count
                return result
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to count complaints by category: {exc}") from exc

    def count_complaints_by_priority(self) -> Dict[str, int]:
        try:
            with self._connect() as conn:
                result = {}
                rows = conn.execute(
                    """
                    SELECT a.priority, COUNT(c.id)
                    FROM complaints c
                    LEFT JOIN ai_analysis a ON c.id = a.complaint_id
                    GROUP BY a.priority
                    """
                ).fetchall()
                for priority, count in rows:
                    if count > 0:
                        key = priority if priority is not None else UNANALYZED_LABEL
                        result[key] = count
                return result
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to count complaints by priority: {exc}") from exc

    def count_complaints_by_status(self) -> Dict[str, int]:
        try:
            with self._connect() as conn:
                result = {}
                rows = conn.execute(
                    "SELECT status, COUNT(*) FROM complaints GROUP BY status"
                ).fetchall()
                for status, count in rows:
                    if count > 0:
                        result[status] = count
                return result
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to count complaints by status: {exc}") from exc

    def count_complaints_by_department(self) -> Dict[str, int]:
        try:
            with self._connect() as conn:
                result = {}
                rows = conn.execute(
                    """
                    SELECT d.name, COUNT(c.id)
                    FROM complaints c
                    LEFT JOIN departments d ON c.department_id = d.id
                    GROUP BY c.department_id
                    """
                ).fetchall()
                for d_name, count in rows:
                    if count > 0:
                        key = d_name if d_name is not None else UNASSIGNED_DEPARTMENT_LABEL
                        result[key] = count
                return result
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to count complaints by department: {exc}") from exc

    def get_resolution_time_stats(self) -> Tuple[Optional[float], Optional[float], Optional[float], int]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT
                        AVG((JULIANDAY(resolved_at) - JULIANDAY(created_at)) * 24.0),
                        MIN((JULIANDAY(resolved_at) - JULIANDAY(created_at)) * 24.0),
                        MAX((JULIANDAY(resolved_at) - JULIANDAY(created_at)) * 24.0),
                        COUNT(*)
                    FROM complaints
                    WHERE resolved_at IS NOT NULL
                    """
                ).fetchone()
                return (
                    row[0] if row[0] is not None else None,
                    row[1] if row[1] is not None else None,
                    row[2] if row[2] is not None else None,
                    row[3] if row[3] is not None else 0,
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch resolution time stats: {exc}") from exc

    def get_complaint_trends(self, group_by: str) -> List[Tuple[str, int]]:
        fmt_map = {
            "day": "%Y-%m-%d",
            "week": "%Y-W%W",
            "month": "%Y-%m",
        }
        if group_by not in fmt_map:
            raise DatabaseError(f"Invalid group_by interval: {group_by!r}")
        fmt = fmt_map[group_by]
        try:
            with self._connect() as conn:
                return conn.execute(
                    f"SELECT STRFTIME('{fmt}', created_at) AS period, COUNT(*) FROM complaints GROUP BY period ORDER BY period ASC"
                ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch complaint trends: {exc}") from exc

    # City Risk Indicator Engine (Req #20)
    def get_city_health_risk(self) -> Dict:
        try:
            with self._connect() as conn:
                critical_count = conn.execute(
                    "SELECT COUNT(*) FROM ai_analysis a JOIN complaints c ON a.complaint_id = c.id WHERE a.priority IN ('Critical', 'High') AND c.status != 'resolved'"
                ).fetchone()[0]

                if critical_count >= 3:
                    level = "RED"
                    label = "High Alert / Heavy Complaint Load"
                elif critical_count >= 1:
                    level = "ORANGE"
                    label = "Moderate Alert / Active Pipeline"
                else:
                    level = "GREEN"
                    label = "Optimal City Operations"

                return {"risk_level": level, "description": label, "critical_active_count": critical_count}
        except sqlite3.Error as exc:
            return {"risk_level": "GREEN", "description": "Normal Operations", "critical_active_count": 0}
