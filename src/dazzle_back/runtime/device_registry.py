"""
Device registry for push notifications.

Manages device tokens for mobile push notifications.
Supports both SQLite (dev) and PostgreSQL (production) backends.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dazzle_back.runtime.db_backend import DualBackendMixin

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


class DeviceRegistry(DualBackendMixin):
    """
    Device registry for push notifications.

    Manages device registrations and push tokens.
    Supports both SQLite (dev) and PostgreSQL (production) backends.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        database_url: str | None = None,
    ):
        """
        Initialize device registry.

        Args:
            db_path: Path to SQLite database (default: .dazzle/devices.db)
            database_url: PostgreSQL connection URL (takes precedence over db_path)
        """
        self._init_backend(db_path, database_url, default_path=".dazzle/devices.db")
        self._init_db()

    def _get_connection(self) -> Any:
        """Get a database connection."""
        return self._get_sync_connection()

    def _init_db(self) -> None:
        """Initialize database tables."""
        if self._use_postgres:
            self._init_postgres_db()
        else:
            self._init_sqlite_db()

    def _init_sqlite_db(self) -> None:
        """Initialize SQLite database tables."""
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

    def _init_postgres_db(self) -> None:
        """Initialize PostgreSQL database tables."""
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

    def _exec(self, conn: Any, query: str, params: tuple[object, ...] = ()) -> Any:
        """Execute a query on a connection, handling backend differences."""
        if self._use_postgres:
            query = query.replace("?", "%s")
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor
        else:
            return conn.execute(query, params)

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
            existing = self._exec(
                conn,
                """
                SELECT id FROM devices
                WHERE user_id = ? AND push_token = ?
                """,
                (str(user_id), push_token),
            ).fetchone()

            if existing:
                # Update existing record
                self._exec(
                    conn,
                    """
                    UPDATE devices
                    SET platform = ?, device_name = ?, app_version = ?,
                        os_version = ?, is_active = ?
                    WHERE id = ?
                    """,
                    (
                        platform.value,
                        device_name,
                        app_version,
                        os_version,
                        self._bool_to_db(True),
                        existing["id"],
                    ),
                )
                device_id = existing["id"]
            else:
                # Insert new record
                self._exec(
                    conn,
                    """
                    INSERT INTO devices
                        (id, user_id, platform, push_token, device_name,
                         app_version, os_version, created_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        self._bool_to_db(True),
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
            params: list[Any] = [str(user_id)]

            if platform:
                query += " AND platform = ?"
                params.append(platform.value)

            if active_only:
                query += " AND is_active = ?"
                params.append(self._bool_to_db(True))

            query += " ORDER BY created_at DESC"

            rows = self._exec(conn, query, tuple(params)).fetchall()

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
                    is_active=self._db_to_bool(row["is_active"]),
                )
                for row in rows
            ]

    def get_device(self, device_id: str) -> DeviceRecord | None:
        """Get device by ID."""
        with self._get_connection() as conn:
            row = self._exec(
                conn,
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
                is_active=self._db_to_bool(row["is_active"]),
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
                cursor = self._exec(
                    conn,
                    "UPDATE devices SET is_active = ? WHERE id = ? AND user_id = ?",
                    (self._bool_to_db(False), device_id, str(user_id)),
                )
            else:
                cursor = self._exec(
                    conn,
                    "UPDATE devices SET is_active = ? WHERE id = ?",
                    (self._bool_to_db(False), device_id),
                )
            conn.commit()
            return bool(cursor.rowcount > 0)

    def mark_device_used(self, device_id: str) -> bool:
        """Update last_used_at timestamp."""
        with self._get_connection() as conn:
            cursor = self._exec(
                conn,
                "UPDATE devices SET last_used_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), device_id),
            )
            conn.commit()
            return bool(cursor.rowcount > 0)

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
            cursor = self._exec(
                conn,
                "UPDATE devices SET is_active = ? WHERE push_token = ?",
                (self._bool_to_db(False), push_token),
            )
            conn.commit()
            return int(cursor.rowcount)

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
            cursor = self._exec(
                conn,
                """
                DELETE FROM devices
                WHERE is_active = ? AND created_at < ?
                """,
                (self._bool_to_db(False), cutoff.isoformat()),
            )
            conn.commit()
            return int(cursor.rowcount)


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
