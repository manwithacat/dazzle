"""
Device registry for push notifications.

Manages device tokens for mobile push notifications.
Uses PostgreSQL (psycopg v3) exclusively.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    import psycopg
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
    Uses PostgreSQL (psycopg v3) exclusively.
    """

    def __init__(
        self,
        database_url: str,
    ):
        """
        Initialize device registry.

        Args:
            database_url: PostgreSQL connection URL
        """
        # Normalize Heroku's postgres:// to postgresql://
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        self._database_url = database_url
        self._init_db()

    def _get_connection(self) -> psycopg.Connection[dict[str, Any]]:
        """Get a PostgreSQL database connection."""
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self._database_url, row_factory=dict_row)

    def _init_db(self) -> None:
        """Initialize database tables."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
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
                    is_active BOOLEAN DEFAULT TRUE,
                    UNIQUE(user_id, push_token)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_devices_user_id
                    ON devices(user_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_devices_platform
                    ON devices(platform)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_devices_active
                    ON devices(user_id, is_active)
            """)
            conn.commit()
        finally:
            conn.close()

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

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Check if token already exists for this user
            cursor.execute(
                """
                SELECT id FROM devices
                WHERE user_id = %s AND push_token = %s
                """,
                (str(user_id), push_token),
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing record
                cursor.execute(
                    """
                    UPDATE devices
                    SET platform = %s, device_name = %s, app_version = %s,
                        os_version = %s, is_active = %s
                    WHERE id = %s
                    """,
                    (
                        platform.value,
                        device_name,
                        app_version,
                        os_version,
                        True,
                        existing["id"],
                    ),
                )
                device_id = existing["id"]
            else:
                # Insert new record
                cursor.execute(
                    """
                    INSERT INTO devices
                        (id, user_id, platform, push_token, device_name,
                         app_version, os_version, created_at, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        True,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

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
        conn = self._get_connection()
        try:
            query = "SELECT * FROM devices WHERE user_id = %s"
            params: list[Any] = [str(user_id)]

            if platform:
                query += " AND platform = %s"
                params.append(platform.value)

            if active_only:
                query += " AND is_active = %s"
                params.append(True)

            query += " ORDER BY created_at DESC"

            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

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
        finally:
            conn.close()

    def get_device(self, device_id: str) -> DeviceRecord | None:
        """Get device by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM devices WHERE id = %s",
                (device_id,),
            )
            row = cursor.fetchone()

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
        finally:
            conn.close()

    def unregister_device(self, device_id: str, user_id: UUID | None = None) -> bool:
        """
        Unregister a device.

        Args:
            device_id: Device ID
            user_id: User ID for ownership verification (optional)

        Returns:
            True if device was unregistered
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if user_id:
                cursor.execute(
                    "UPDATE devices SET is_active = %s WHERE id = %s AND user_id = %s",
                    (False, device_id, str(user_id)),
                )
            else:
                cursor.execute(
                    "UPDATE devices SET is_active = %s WHERE id = %s",
                    (False, device_id),
                )
            conn.commit()
            return bool(cursor.rowcount > 0)
        finally:
            conn.close()

    def mark_device_used(self, device_id: str) -> bool:
        """Update last_used_at timestamp."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE devices SET last_used_at = %s WHERE id = %s",
                (datetime.now(UTC).isoformat(), device_id),
            )
            conn.commit()
            return bool(cursor.rowcount > 0)
        finally:
            conn.close()

    def invalidate_token(self, push_token: str) -> int:
        """
        Invalidate a push token (mark as inactive).

        Called when FCM reports a token as invalid.

        Args:
            push_token: The invalid push token

        Returns:
            Number of devices affected
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE devices SET is_active = %s WHERE push_token = %s",
                (False, push_token),
            )
            conn.commit()
            return int(cursor.rowcount)
        finally:
            conn.close()

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

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM devices
                WHERE is_active = %s AND created_at < %s
                """,
                (False, cutoff.isoformat()),
            )
            conn.commit()
            return int(cursor.rowcount)
        finally:
            conn.close()


# =============================================================================
# Device Routes
# =============================================================================


def create_device_routes(
    device_registry: DeviceRegistry,
    get_current_user: Any,  # Auth dependency
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
        auth: Any = Depends(get_current_user),
    ) -> dict[str, Any]:
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
        auth: Any = Depends(get_current_user),
    ) -> dict[str, Any]:
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
        auth: Any = Depends(get_current_user),
    ) -> dict[str, str]:
        """Unregister a device."""
        success = device_registry.unregister_device(device_id, auth.user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"status": "unregistered"}

    return router
