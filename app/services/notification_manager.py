"""NotificationManager: creates and retrieves in-app notifications only.

No email, SMS, or push delivery is implemented here -- notifications are
purely stored records read back by the application UI.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from app.services.db_manager import DatabaseError, DatabaseManager


class NotificationManagerError(Exception):
    """Raised when a notification operation fails."""


@dataclass
class Notification:
    user_id: int
    message: str
    complaint_id: Optional[int] = None
    id: Optional[int] = None
    is_read: bool = False
    created_at: Optional[datetime] = None


class NotificationManager:
    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db_manager = db_manager

    def notify(
        self,
        user_id: int,
        message: str,
        complaint_id: Optional[int] = None,
    ) -> Notification:
        if not message or not message.strip():
            raise NotificationManagerError("Notification message must not be empty.")

        cleaned_message = message.strip()
        try:
            notification_id = self._db_manager.save_notification(
                user_id=user_id,
                message=cleaned_message,
                complaint_id=complaint_id,
            )
        except DatabaseError as exc:
            raise NotificationManagerError(f"Failed to create notification: {exc}") from exc

        return Notification(
            id=notification_id,
            user_id=user_id,
            complaint_id=complaint_id,
            message=cleaned_message,
        )

    def mark_as_read(self, notification_id: int) -> None:
        try:
            self._db_manager.mark_notification_read(notification_id)
        except DatabaseError as exc:
            raise NotificationManagerError(f"Failed to mark notification as read: {exc}") from exc

    def get_notifications_for_user(self, user_id: int) -> List[Notification]:
        try:
            rows = self._db_manager.get_notifications_for_user(user_id)
        except DatabaseError as exc:
            raise NotificationManagerError(f"Failed to fetch notifications: {exc}") from exc

        return [
            Notification(
                id=row[0],
                user_id=row[1],
                complaint_id=row[2],
                message=row[3],
                is_read=bool(row[4]),
                created_at=row[5],
            )
            for row in rows
        ]
