"""
Push notification service for mobile clients.

Supports Firebase Cloud Messaging (FCM) for iOS and Android.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from dazzle_dnr_back.runtime.device_registry import DevicePlatform, DeviceRegistry


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class PushConfig:
    """
    Push notification configuration.

    Supports FCM for cross-platform push notifications.
    """

    # Firebase Cloud Messaging
    fcm_credentials_path: str | None = None
    fcm_credentials_json: dict[str, Any] | None = None

    # Defaults
    default_sound: str = "default"
    default_badge: int | None = None
    default_ttl_seconds: int = 86400  # 24 hours


# =============================================================================
# Notification Models
# =============================================================================


class NotificationPriority(str, Enum):
    """Push notification priority."""

    NORMAL = "normal"
    HIGH = "high"


class PushNotification(BaseModel):
    """
    Push notification payload.

    Cross-platform notification format.
    """

    title: str = Field(description="Notification title")
    body: str = Field(description="Notification body")
    data: dict[str, Any] | None = Field(default=None, description="Custom data payload")
    image_url: str | None = Field(default=None, description="Image URL for rich notifications")
    sound: str | None = Field(default=None, description="Sound name")
    badge: int | None = Field(default=None, description="Badge count (iOS)")
    priority: NotificationPriority = Field(
        default=NotificationPriority.HIGH, description="Notification priority"
    )
    ttl_seconds: int | None = Field(default=None, description="Time to live in seconds")

    # Routing
    click_action: str | None = Field(default=None, description="Action on notification click")
    channel_id: str | None = Field(default=None, description="Android notification channel")


@dataclass
class PushResult:
    """Result of sending a push notification."""

    success: bool
    device_id: str
    message_id: str | None = None
    error: str | None = None
    error_code: str | None = None


@dataclass
class BatchPushResult:
    """Result of sending batch push notifications."""

    total: int
    success_count: int
    failure_count: int
    results: list[PushResult] = field(default_factory=list)

    @property
    def all_success(self) -> bool:
        return self.failure_count == 0


# =============================================================================
# Push Service
# =============================================================================


class PushNotificationService:
    """
    Push notification service.

    Sends notifications via Firebase Cloud Messaging.
    """

    def __init__(
        self,
        device_registry: DeviceRegistry,
        config: PushConfig | None = None,
    ):
        """
        Initialize push notification service.

        Args:
            device_registry: Device registry for looking up push tokens
            config: Push notification configuration
        """
        self.device_registry = device_registry
        self.config = config or PushConfig()
        self._fcm_app = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Initialize FCM if not already done."""
        if self._initialized:
            return

        if not self.config.fcm_credentials_path and not self.config.fcm_credentials_json:
            raise PushError(
                "FCM credentials not configured. Set fcm_credentials_path or fcm_credentials_json",
                code="not_configured",
            )

        try:
            import firebase_admin
            from firebase_admin import credentials
        except ImportError:
            raise PushError(
                "firebase-admin not installed. Install with: pip install firebase-admin",
                code="missing_dependency",
            )

        # Initialize Firebase app
        if self.config.fcm_credentials_path:
            cred = credentials.Certificate(self.config.fcm_credentials_path)
        else:
            cred = credentials.Certificate(self.config.fcm_credentials_json)

        try:
            self._fcm_app = firebase_admin.get_app()
        except ValueError:
            self._fcm_app = firebase_admin.initialize_app(cred)

        self._initialized = True

    async def send_to_user(
        self,
        user_id: UUID,
        notification: PushNotification,
        platforms: list[DevicePlatform] | None = None,
    ) -> BatchPushResult:
        """
        Send notification to all devices for a user.

        Args:
            user_id: Target user ID
            notification: Notification to send
            platforms: Filter by platforms (None = all)

        Returns:
            Batch result with individual device results
        """

        devices = self.device_registry.get_user_devices(user_id, active_only=True)

        if platforms:
            devices = [d for d in devices if d.platform in platforms]

        if not devices:
            return BatchPushResult(total=0, success_count=0, failure_count=0, results=[])

        results = []
        for device in devices:
            result = await self.send_to_device(device.push_token, notification, device.id)
            results.append(result)

            # Mark device as used
            if result.success:
                self.device_registry.mark_device_used(device.id)
            elif result.error_code in ("invalid_token", "unregistered"):
                # Invalidate the token
                self.device_registry.invalidate_token(device.push_token)

        success_count = sum(1 for r in results if r.success)
        failure_count = len(results) - success_count

        return BatchPushResult(
            total=len(results),
            success_count=success_count,
            failure_count=failure_count,
            results=results,
        )

    async def send_to_device(
        self,
        push_token: str,
        notification: PushNotification,
        device_id: str | None = None,
    ) -> PushResult:
        """
        Send notification to a specific device.

        Args:
            push_token: FCM push token
            notification: Notification to send
            device_id: Device ID for tracking

        Returns:
            Push result
        """
        self._ensure_initialized()

        try:
            from firebase_admin import messaging
        except ImportError:
            raise PushError(
                "firebase-admin not installed",
                code="missing_dependency",
            )

        # Build FCM message
        message = self._build_fcm_message(push_token, notification)

        try:
            # Send message
            response = messaging.send(message)

            return PushResult(
                success=True,
                device_id=device_id or push_token[:16],
                message_id=response,
            )

        except messaging.UnregisteredError:
            return PushResult(
                success=False,
                device_id=device_id or push_token[:16],
                error="Device token is no longer valid",
                error_code="unregistered",
            )

        except messaging.SenderIdMismatchError:
            return PushResult(
                success=False,
                device_id=device_id or push_token[:16],
                error="Token belongs to different sender",
                error_code="sender_mismatch",
            )

        except messaging.QuotaExceededError:
            return PushResult(
                success=False,
                device_id=device_id or push_token[:16],
                error="FCM quota exceeded",
                error_code="quota_exceeded",
            )

        except Exception as e:
            return PushResult(
                success=False,
                device_id=device_id or push_token[:16],
                error=str(e),
                error_code="send_error",
            )

    def _build_fcm_message(self, push_token: str, notification: PushNotification):
        """Build FCM Message object from PushNotification."""
        from firebase_admin import messaging

        # Build notification payload
        fcm_notification = messaging.Notification(
            title=notification.title,
            body=notification.body,
            image=notification.image_url,
        )

        # Build Android config
        android_config = messaging.AndroidConfig(
            priority="high" if notification.priority == NotificationPriority.HIGH else "normal",
            ttl=notification.ttl_seconds or self.config.default_ttl_seconds,
            notification=messaging.AndroidNotification(
                sound=notification.sound or self.config.default_sound,
                channel_id=notification.channel_id,
                click_action=notification.click_action,
            ),
        )

        # Build iOS config
        apns_config = messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    sound=notification.sound or self.config.default_sound,
                    badge=notification.badge or self.config.default_badge,
                ),
            ),
        )

        # Build message
        return messaging.Message(
            token=push_token,
            notification=fcm_notification,
            data=notification.data or {},
            android=android_config,
            apns=apns_config,
        )

    async def send_to_topic(
        self,
        topic: str,
        notification: PushNotification,
    ) -> PushResult:
        """
        Send notification to a topic.

        All devices subscribed to the topic will receive the notification.

        Args:
            topic: FCM topic name
            notification: Notification to send

        Returns:
            Push result
        """
        self._ensure_initialized()

        try:
            from firebase_admin import messaging
        except ImportError:
            raise PushError(
                "firebase-admin not installed",
                code="missing_dependency",
            )

        # Build notification
        fcm_notification = messaging.Notification(
            title=notification.title,
            body=notification.body,
            image=notification.image_url,
        )

        message = messaging.Message(
            topic=topic,
            notification=fcm_notification,
            data=notification.data or {},
        )

        try:
            response = messaging.send(message)
            return PushResult(
                success=True,
                device_id=f"topic:{topic}",
                message_id=response,
            )
        except Exception as e:
            return PushResult(
                success=False,
                device_id=f"topic:{topic}",
                error=str(e),
                error_code="send_error",
            )

    async def subscribe_to_topic(
        self,
        push_tokens: list[str],
        topic: str,
    ) -> dict[str, int]:
        """
        Subscribe devices to a topic.

        Args:
            push_tokens: List of FCM tokens
            topic: Topic name

        Returns:
            Dict with success_count and failure_count
        """
        self._ensure_initialized()

        try:
            from firebase_admin import messaging
        except ImportError:
            raise PushError(
                "firebase-admin not installed",
                code="missing_dependency",
            )

        response = messaging.subscribe_to_topic(push_tokens, topic)

        return {
            "success_count": response.success_count,
            "failure_count": response.failure_count,
        }

    async def unsubscribe_from_topic(
        self,
        push_tokens: list[str],
        topic: str,
    ) -> dict[str, int]:
        """
        Unsubscribe devices from a topic.

        Args:
            push_tokens: List of FCM tokens
            topic: Topic name

        Returns:
            Dict with success_count and failure_count
        """
        self._ensure_initialized()

        try:
            from firebase_admin import messaging
        except ImportError:
            raise PushError(
                "firebase-admin not installed",
                code="missing_dependency",
            )

        response = messaging.unsubscribe_from_topic(push_tokens, topic)

        return {
            "success_count": response.success_count,
            "failure_count": response.failure_count,
        }


# =============================================================================
# Exceptions
# =============================================================================


class PushError(Exception):
    """Push notification error."""

    def __init__(self, message: str, code: str = "push_error"):
        super().__init__(message)
        self.message = message
        self.code = code


# =============================================================================
# Factory Functions
# =============================================================================


def create_push_service(
    device_registry: DeviceRegistry,
    fcm_credentials_path: str | None = None,
    fcm_credentials_json: dict[str, Any] | None = None,
) -> PushNotificationService:
    """
    Create a push notification service.

    Args:
        device_registry: Device registry instance
        fcm_credentials_path: Path to Firebase service account JSON
        fcm_credentials_json: Firebase credentials as dict

    Returns:
        Configured push notification service
    """
    config = PushConfig(
        fcm_credentials_path=fcm_credentials_path,
        fcm_credentials_json=fcm_credentials_json,
    )
    return PushNotificationService(device_registry, config)
