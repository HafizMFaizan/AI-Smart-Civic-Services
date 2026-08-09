"""DatabaseManager: the only module allowed to run SQLite operations."""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from app.models.ai_analysis import AIAnalysis, ComplaintCategory
from app.models.complaint import ComplaintStatus

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = _PROJECT_ROOT / "database" / "civic_services.db"
SCHEMA_PATH = _PROJECT_ROOT / "database" / "schema.sql"

# Explicit buckets for analytics aggregates -- never real department names or
# ai_analysis categories, so they can't collide with real data.
UNASSIGNED_DEPARTMENT_LABEL = "Unassigned"
UNANALYZED_LABEL = "Unanalyzed"

# Seeded automatically on a fresh database so the admin API is reachable at
# all -- without this, POST /api/users only ever creates citizens, and a
# brand-new deployment would have no way to bootstrap its first admin.
DEFAULT_ADMIN_NAME = "Default Admin"
DEFAULT_ADMIN_EMAIL = "admin@civicservices.local"


class DatabaseError(Exception):
    """Raised when a database operation fails."""


class DuplicateEmailError(DatabaseError):
    """Raised when creating a user with an email that is already registered."""


class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or str(DEFAULT_DB_PATH)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    def initialize_database(self) -> None:
        try:
            with self._connect() as conn:
                with open(SCHEMA_PATH, "r", encoding="utf-8") as schema_file:
                    conn.executescript(schema_file.read())
                self._migrate_resolved_at_column(conn)
                self._seed_default_admin(conn)
        except (sqlite3.Error, OSError) as exc:
            raise DatabaseError(f"Failed to initialize database: {exc}") from exc

    @staticmethod
    def _seed_default_admin(conn: sqlite3.Connection) -> None:
        """Ensure at least one admin user exists.

        Idempotent: skipped whenever any admin already exists, no matter how
        many other users exist. On a genuinely fresh database this is the
        very first row inserted into `users`, so it lands at id 1 via
        AUTOINCREMENT -- but that id is a consequence of running first, never
        hardcoded, so this stays safe to run against a non-empty database too.
        """
        admin_count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin'"
        ).fetchone()[0]
        if admin_count > 0:
            return

        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (DEFAULT_ADMIN_EMAIL,)
        ).fetchone()
        if existing is not None:
            logger.warning(
                "No admin user exists, but email %s is already taken by "
                "user_id=%s; skipping automatic admin seeding.",
                DEFAULT_ADMIN_EMAIL,
                existing[0],
            )
            return

        cursor = conn.execute(
            "INSERT INTO users (name, email, role) VALUES (?, ?, 'admin')",
            (DEFAULT_ADMIN_NAME, DEFAULT_ADMIN_EMAIL),
        )
        logger.info(
            "No admin user existed; seeded default admin user_id=%s (email=%s). "
            "Use this id in the X-User-Id header for admin endpoints.",
            cursor.lastrowid,
            DEFAULT_ADMIN_EMAIL,
        )

    @staticmethod
    def _migrate_resolved_at_column(conn: sqlite3.Connection) -> None:
        """Add complaints.resolved_at to databases created before Phase 4A.

        CREATE TABLE IF NOT EXISTS never alters an existing table, so a
        database initialized under an earlier schema version needs this
        explicit, additive, data-preserving migration. Safe to run on every
        startup: a no-op once the column exists.
        """
        columns = [row[1] for row in conn.execute("PRAGMA table_info(complaints)").fetchall()]
        if "resolved_at" not in columns:
            conn.execute("ALTER TABLE complaints ADD COLUMN resolved_at TIMESTAMP")

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

    def save_complaint(
        self,
        user_id: int,
        description: str,
        department_id: Optional[int] = None,
        location: Optional[str] = None,
    ) -> int:
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO complaints (user_id, department_id, description, location) "
                    "VALUES (?, ?, ?, ?)",
                    (user_id, department_id, description, location),
                )
                return cursor.lastrowid
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to save complaint: {exc}") from exc

    def save_ai_analysis(self, analysis: AIAnalysis) -> int:
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO ai_analysis
                        (complaint_id, category, priority, summary, model_name,
                         confidence, ai_status)
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
                return cursor.lastrowid
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to save AI analysis: {exc}") from exc

    def department_exists(self, department_id: int) -> bool:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT 1 FROM departments WHERE id = ?", (department_id,)
                ).fetchone()
                return row is not None
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to check department existence: {exc}") from exc

    def get_or_create_department(self, name: str, category: ComplaintCategory) -> int:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT id FROM departments WHERE name = ?", (name,)
                ).fetchone()
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
                    "UPDATE complaints SET department_id = ? WHERE id = ?",
                    (department_id, complaint_id),
                )
                if cursor.rowcount == 0:
                    raise DatabaseError(
                        f"No complaint found with id {complaint_id}; "
                        f"department was not updated."
                    )
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to update complaint department: {exc}") from exc

    def update_complaint_status(self, complaint_id: int, status: ComplaintStatus) -> None:
        if not isinstance(status, ComplaintStatus):
            raise DatabaseError(f"Invalid complaint status: {status!r}")
        try:
            with self._connect() as conn:
                # resolved_at reflects only the 'resolved' status specifically
                # (not 'closed'), and is overwritten every time a complaint
                # re-enters 'resolved' after being reopened -- it always
                # reflects the latest resolution, not the first one.
                if status == ComplaintStatus.RESOLVED:
                    cursor = conn.execute(
                        "UPDATE complaints SET status = ?, resolved_at = CURRENT_TIMESTAMP "
                        "WHERE id = ?",
                        (status.value, complaint_id),
                    )
                else:
                    cursor = conn.execute(
                        "UPDATE complaints SET status = ? WHERE id = ?",
                        (status.value, complaint_id),
                    )
                if cursor.rowcount == 0:
                    raise DatabaseError(
                        f"No complaint found with id {complaint_id}; status was not updated."
                    )
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to update complaint status: {exc}") from exc

    def save_notification(
        self,
        user_id: int,
        message: str,
        complaint_id: Optional[int] = None,
    ) -> int:
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO notifications (user_id, complaint_id, message) "
                    "VALUES (?, ?, ?)",
                    (user_id, complaint_id, message),
                )
                return cursor.lastrowid
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to save notification: {exc}") from exc

    def mark_notification_read(self, notification_id: int) -> None:
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,)
                )
                if cursor.rowcount == 0:
                    raise DatabaseError(f"No notification found with id {notification_id}.")
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to mark notification as read: {exc}") from exc

    def get_notifications_for_user(self, user_id: int) -> List[Tuple]:
        try:
            with self._connect() as conn:
                return conn.execute(
                    "SELECT id, user_id, complaint_id, message, is_read, created_at "
                    "FROM notifications WHERE user_id = ? ORDER BY created_at DESC",
                    (user_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch notifications: {exc}") from exc

    def count_total_complaints(self) -> int:
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()
                return row[0]
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to count total complaints: {exc}") from exc

    def count_complaints_by_category(self) -> Dict[str, int]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT COALESCE(a.category, '{UNANALYZED_LABEL}'), COUNT(c.id)
                    FROM complaints c
                    LEFT JOIN ai_analysis a ON a.complaint_id = c.id
                    GROUP BY COALESCE(a.category, '{UNANALYZED_LABEL}')
                    """
                ).fetchall()
                return {category: count for category, count in rows}
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to count complaints by category: {exc}") from exc

    def count_complaints_by_priority(self) -> Dict[str, int]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT COALESCE(a.priority, '{UNANALYZED_LABEL}'), COUNT(c.id)
                    FROM complaints c
                    LEFT JOIN ai_analysis a ON a.complaint_id = c.id
                    GROUP BY COALESCE(a.priority, '{UNANALYZED_LABEL}')
                    """
                ).fetchall()
                return {priority: count for priority, count in rows}
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to count complaints by priority: {exc}") from exc

    def count_complaints_by_status(self) -> Dict[str, int]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT status, COUNT(*) FROM complaints GROUP BY status"
                ).fetchall()
                return {status: count for status, count in rows}
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to count complaints by status: {exc}") from exc

    def create_user(
        self,
        name: str,
        email: str,
        phone: Optional[str] = None,
    ) -> int:
        # Role is always 'citizen' -- this is a public, unauthenticated path,
        # so it must never accept a caller-supplied role (self-promotion risk).
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO users (name, email, phone, role) VALUES (?, ?, ?, 'citizen')",
                    (name, email, phone),
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise DuplicateEmailError(f"Email already registered: {email!r}") from exc
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to create user: {exc}") from exc

    def get_user_role(self, user_id: int) -> Optional[str]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT role FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                return row[0] if row is not None else None
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch user role: {exc}") from exc

    def get_complaint_owner(self, complaint_id: int) -> Optional[int]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT user_id FROM complaints WHERE id = ?", (complaint_id,)
                ).fetchone()
                return row[0] if row is not None else None
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch complaint owner: {exc}") from exc

    def get_complaints_for_user(self, user_id: int) -> List[Tuple]:
        try:
            with self._connect() as conn:
                return conn.execute(
                    """
                    SELECT c.id, c.description, c.location, c.status, c.department_id,
                           d.name, a.category, a.priority, a.summary, a.ai_status, c.created_at
                    FROM complaints c
                    LEFT JOIN departments d ON d.id = c.department_id
                    LEFT JOIN ai_analysis a ON a.complaint_id = c.id
                    WHERE c.user_id = ?
                    ORDER BY c.created_at DESC
                    """,
                    (user_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch complaints for user: {exc}") from exc

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
    ) -> List[Tuple]:
        """Fetch complaints for the admin dashboard, optionally filtered.

        Every parameter is optional and defaults to None; calling this with
        no arguments reproduces the exact pre-Phase-4A behavior (all
        complaints, unfiltered). All filters combine with AND semantics.
        `category`/`priority` accept UNANALYZED_LABEL to match complaints
        with no ai_analysis row yet, consistent with the analytics buckets.
        """
        conditions: List[str] = []
        params: List = []

        if category is not None:
            if category == UNANALYZED_LABEL:
                conditions.append("a.category IS NULL")
            else:
                conditions.append("a.category = ?")
                params.append(category)

        if priority is not None:
            if priority == UNANALYZED_LABEL:
                conditions.append("a.priority IS NULL")
            else:
                conditions.append("a.priority = ?")
                params.append(priority)

        if status is not None:
            conditions.append("c.status = ?")
            params.append(status)

        if department_id is not None:
            conditions.append("c.department_id = ?")
            params.append(department_id)

        if location is not None:
            conditions.append("c.location LIKE ?")
            params.append(f"%{location}%")

        if search is not None:
            conditions.append("(c.description LIKE ? OR c.location LIKE ?)")
            params.append(f"%{search}%")
            params.append(f"%{search}%")

        if date_from is not None:
            conditions.append("date(c.created_at) >= date(?)")
            params.append(date_from)

        if date_to is not None:
            conditions.append("date(c.created_at) <= date(?)")
            params.append(date_to)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        try:
            with self._connect() as conn:
                return conn.execute(
                    f"""
                    SELECT c.id, c.user_id, u.name, u.email, c.description, c.location,
                           c.status, c.department_id, d.name, a.category, a.priority,
                           a.summary, a.ai_status, c.created_at
                    FROM complaints c
                    JOIN users u ON u.id = c.user_id
                    LEFT JOIN departments d ON d.id = c.department_id
                    LEFT JOIN ai_analysis a ON a.complaint_id = c.id
                    {where_clause}
                    ORDER BY c.created_at DESC
                    """,
                    params,
                ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch all complaints: {exc}") from exc

    def get_complaint_trends(self, group_by: str) -> List[Tuple[str, int]]:
        bucket_expressions = {
            "day": "strftime('%Y-%m-%d', created_at)",
            "week": "strftime('%Y-W%W', created_at)",
            "month": "strftime('%Y-%m', created_at)",
        }
        bucket_expr = bucket_expressions.get(group_by)
        if bucket_expr is None:
            raise DatabaseError(f"Invalid group_by value: {group_by!r}")

        try:
            with self._connect() as conn:
                return conn.execute(
                    f"""
                    SELECT {bucket_expr} AS period, COUNT(*)
                    FROM complaints
                    GROUP BY period
                    ORDER BY period
                    """
                ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to compute complaint trends: {exc}") from exc

    def get_resolution_time_stats(
        self,
    ) -> Tuple[Optional[float], Optional[float], Optional[float], int]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT AVG(hours), MIN(hours), MAX(hours), COUNT(*)
                    FROM (
                        SELECT (julianday(resolved_at) - julianday(created_at)) * 24 AS hours
                        FROM complaints
                        WHERE resolved_at IS NOT NULL
                    )
                    """
                ).fetchone()
                return row[0], row[1], row[2], row[3]
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to compute resolution time stats: {exc}") from exc

    def count_complaints_by_department(self) -> Dict[str, int]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT COALESCE(d.name, '{UNASSIGNED_DEPARTMENT_LABEL}'), COUNT(c.id)
                    FROM complaints c
                    LEFT JOIN departments d ON d.id = c.department_id
                    GROUP BY COALESCE(d.name, '{UNASSIGNED_DEPARTMENT_LABEL}')
                    """
                ).fetchall()
                return {name: count for name, count in rows}
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to count complaints by department: {exc}") from exc
