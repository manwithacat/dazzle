"""
Device registry for push notifications.

Manages device tokens for mobile push notifications.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from fastapi import APIRouter


# =============================================================================
# Device Models
# =============================================================================


class DevicePlatform(StrEnum):
    """Supported device platforms."""

    IOS = "ios"
    ANDROID = "android"
    WEB = "web"  # For PWA/web push


class DeviceRecord(BaseModel):
    """
    Device registration record.

    Stores push token and device metadata.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Device registration ID")
    user_id: UUID = Field(description="User ID")
    platform: DevicePlatform = Field(description="Device platform")
    push_token: str = Field(description="Push notification token")
    device_name: str | None = Field(default=None, description="User-friendly device name")
    app_version: str | None = Field(default=None, description="App version")
    os_version: str | None = Field(default=None, description="OS version")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = Field(default=None, description="Last push sent")
    is_active: bool = Field(default=True, description="Whether device is active")


# =============================================================================
# Device Registry
# =============================================================================


class DeviceRegistry:
    """
    Device registry for push notifications.

    Manages device registrations and push tokens.
    """

    def __init__(self, db_path: str | Path | None = None):
        """
        Initialize device registry.

        Args:
            db_path: Path to SQLite database (default: .dazzle/devices.db)
        """
        self.db_path = Path(db_path) if db_path else Path(".dazzle/devices.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database tables."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    push_token TEXT NOT NULL,
                    device_name TEXT,
                    app_version TEXT,
                    os_version TEXT,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    is_active INTEGER DEFAULT 1,
                    UNIQUE(user_id, push_token)
                );

                CREATE INDEX IF NOT EXISTS idx_devices_user_id
                    ON devices(user_id);
                CREATE INDEX IF NOT EXISTS idx_devices_platform
                    ON devices(platform);
                CREATE INDEX IF NOT EXISTS idx_devices_active
                    ON devices(user_id, is_active);
            """)
            conn.commit()

    # =========================================================================
    # Device Operations
    # =========================================================================

    def register_device(
        self,
        user_id: UUID,
        platform: DevicePlatform,
        push_token: str,
        device_name: str | None = None,
        app_version: str | None = None,
        os_version: str | None = None,
    ) -> DeviceRecord:
        """
        Register a device for push notifications.

        If the push token already exists for this user, updates the record.

        Args:
            user_id: User ID
            platform: Device platform (ios/android/web)
            push_token: Push notification token from FCM/APNs
            device_name: User-friendly device name
            app_version: App version string
            os_version: OS version string

        Returns:
            Device registration record
        """
        import secrets

        now = datetime.now(UTC)
        device_id = secrets.token_urlsafe(16)

        with self._get_connection() as conn:
            # Check if token already exists for this user
            existing = conn.execute(
                """
                SELECT id FROM devices
                WHERE user_id = ? AND push_token = ?
                """,
                (str(user_id), push_token),
            ).fetchone()

            if existing:
                # Update existing record
                conn.execute(
                    """
                    UPDATE devices
                    SET platform = ?, device_name = ?, app_version = ?,
                        os_version = ?, is_active = 1
                    WHERE id = ?
                    """,
                    (platform.value, device_name, app_version, os_version, existing["id"]),
                )
                device_id = existing["id"]
            else:
                # Insert new record
                conn.execute(
                    """
                    INSERT INTO devices
                        (id, user_id, platform, push_token, device_name,
                         app_version, os_version, created_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        device_id,
                        str(user_id),
                        platform.value,
                        push_token,
                        device_name,
                        app_version,
                        os_version,
                        now.isoformat(),
                    ),
                )
            conn.commit()

        return DeviceRecord(
            id=device_id,
            user_id=user_id,
            platform=platform,
            push_token=push_token,
            device_name=device_name,
            app_version=app_version,
            os_version=os_version,
            created_at=now,
            is_active=True,
        )

    def get_user_devices(
        self,
        user_id: UUID,
        platform: DevicePlatform | None = None,
        active_only: bool = True,
    ) -> list[DeviceRecord]:
        """
        Get all devices for a user.

        Args:
            user_id: User ID
            platform: Filter by platform (optional)
            active_only: Only return active devices

        Returns:
            List of device records
        """
        with self._get_connection() as conn:
            query = "SELECT * FROM devices WHERE user_id = ?"
            params: list = [str(user_id)]

            if platform:
                query += " AND platform = ?"
                params.append(platform.value)

            if active_only:
                query += " AND is_active = 1"

            query += " ORDER BY created_at DESC"

            rows = conn.execute(query, params).fetchall()

            return [
                DeviceRecord(
                    id=row["id"],
                    user_id=UUID(row["user_id"]),
                    platform=DevicePlatform(row["platform"]),
                    push_token=row["push_token"],
                    device_name=row["device_name"],
                    app_version=row["app_version"],
                    os_version=row["os_version"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    last_used_at=(
                        datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None
                    ),
                    is_active=bool(row["is_active"]),
                )
                for row in rows
            ]

    def get_device(self, device_id: str) -> DeviceRecord | None:
        """Get device by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM devices WHERE id = ?",
                (device_id,),
            ).fetchone()

            if not row:
                return None

            return DeviceRecord(
                id=row["id"],
                user_id=UUID(row["user_id"]),
                platform=DevicePlatform(row["platform"]),
                push_token=row["push_token"],
                device_name=row["device_name"],
                app_version=row["app_version"],
                os_version=row["os_version"],
                created_at=datetime.fromisoformat(row["created_at"]),
                last_used_at=(
                    datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None
                ),
                is_active=bool(row["is_active"]),
            )

    def unregister_device(self, device_id: str, user_id: UUID | None = None) -> bool:
        """
        Unregister a device.

        Args:
            device_id: Device ID
            user_id: User ID for ownership verification (optional)

        Returns:
            True if device was unregistered
        """
        with self._get_connection() as conn:
            if user_id:
                cursor = conn.execute(
                    "UPDATE devices SET is_active = 0 WHERE id = ? AND user_id = ?",
                    (device_id, str(user_id)),
                )
            else:
                cursor = conn.execute(
                    "UPDATE devices SET is_active = 0 WHERE id = ?",
                    (device_id,),
                )
            conn.commit()
            return cursor.rowcount > 0

    def mark_device_used(self, device_id: str) -> bool:
        """Update last_used_at timestamp."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE devices SET last_used_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), device_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def invalidate_token(self, push_token: str) -> int:
        """
        Invalidate a push token (mark as inactive).

        Called when FCM reports a token as invalid.

        Args:
            push_token: The invalid push token

        Returns:
            Number of devices affected
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE devices SET is_active = 0 WHERE push_token = ?",
                (push_token,),
            )
            conn.commit()
            return cursor.rowcount

    def cleanup_inactive(self, older_than_days: int = 90) -> int:
        """
        Remove old inactive devices.

        Args:
            older_than_days: Remove inactive devices older than this

        Returns:
            Number of devices removed
        """
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM devices
                WHERE is_active = 0 AND created_at < ?
                """,
                (cutoff.isoformat(),),
            )
            conn.commit()
            return cursor.rowcount


# =============================================================================
# Device Routes
# =============================================================================


def create_device_routes(
    device_registry: DeviceRegistry,
    get_current_user,  # Auth dependency
) -> APIRouter:
    """
    Create device registration routes.

    Args:
        device_registry: Device registry instance
        get_current_user: FastAPI dependency for getting current user

    Returns:
        FastAPI router with device endpoints
    """
    try:
        from fastapi import APIRouter, Depends, HTTPException
    except ImportError:
        raise RuntimeError("FastAPI is required for device routes")

    from pydantic import BaseModel

    router = APIRouter(prefix="/devices", tags=["Devices"])

    class RegisterDeviceRequest(BaseModel):
        platform: DevicePlatform
        push_token: str
        device_name: str | None = None
        app_version: str | None = None
        os_version: str | None = None

    @router.post("/register")
    async def register_device(
        data: RegisterDeviceRequest,
        auth=Depends(get_current_user),
    ):
        """Register device for push notifications."""
        device = device_registry.register_device(
            user_id=auth.user_id,
            platform=data.platform,
            push_token=data.push_token,
            device_name=data.device_name,
            app_version=data.app_version,
            os_version=data.os_version,
        )
        return {
            "id": device.id,
            "platform": device.platform.value,
            "device_name": device.device_name,
            "created_at": device.created_at.isoformat(),
        }

    @router.get("")
    async def list_devices(
        auth=Depends(get_current_user),
    ):
        """List user's registered devices."""
        devices = device_registry.get_user_devices(auth.user_id)
        return {
            "devices": [
                {
                    "id": d.id,
                    "platform": d.platform.value,
                    "device_name": d.device_name,
                    "app_version": d.app_version,
                    "os_version": d.os_version,
                    "created_at": d.created_at.isoformat(),
                    "last_used_at": d.last_used_at.isoformat() if d.last_used_at else None,
                }
                for d in devices
            ],
            "count": len(devices),
        }

    @router.delete("/{device_id}")
    async def unregister_device(
        device_id: str,
        auth=Depends(get_current_user),
    ):
        """Unregister a device."""
        success = device_registry.unregister_device(device_id, auth.user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"status": "unregistered"}

    return router
