"""
SES bounce/complaint webhook handler via SNS notifications.

Handles:
- SNS SubscriptionConfirmation (auto-confirms)
- SES Bounce notifications
- SES Complaint notifications
- SES Delivery notifications
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("dazzle.channels.ses_webhooks")


def _parse_sns_message(body: bytes) -> dict[str, Any]:
    """Parse and validate an SNS message body.

    Args:
        body: Raw request body

    Returns:
        Parsed message dict
    """
    return json.loads(body)  # type: ignore[no-any-return]


async def _confirm_subscription(message: dict[str, Any]) -> bool:
    """Auto-confirm an SNS subscription.

    Args:
        message: SNS SubscriptionConfirmation message

    Returns:
        True if confirmed successfully
    """
    subscribe_url = message.get("SubscribeURL")
    if not subscribe_url:
        logger.error("SNS SubscriptionConfirmation missing SubscribeURL")
        return False

    try:
        import urllib.request

        req = urllib.request.Request(subscribe_url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                logger.info(
                    "SNS subscription confirmed for topic: %s",
                    message.get("TopicArn", "unknown"),
                )
                return True
            logger.error("SNS subscription confirmation failed: HTTP %s", resp.status)
            return False
    except Exception as e:
        logger.error("Failed to confirm SNS subscription: %s", e)
        return False


def _parse_ses_event(notification_message: str) -> dict[str, Any] | None:
    """Parse SES event from SNS notification message.

    Args:
        notification_message: JSON string from SNS Message field

    Returns:
        Parsed SES event dict or None
    """
    try:
        return json.loads(notification_message)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse SES event from SNS notification")
        return None


def _handle_bounce(ses_event: dict[str, Any]) -> dict[str, Any]:
    """Process SES bounce notification.

    Args:
        ses_event: Parsed SES event

    Returns:
        Summary of the bounce event
    """
    bounce = ses_event.get("bounce", {})
    bounce_type = bounce.get("bounceType", "unknown")
    bounce_sub_type = bounce.get("bounceSubType", "unknown")
    recipients = [r.get("emailAddress", "") for r in bounce.get("bouncedRecipients", [])]

    logger.warning(
        "SES bounce: type=%s sub_type=%s recipients=%s",
        bounce_type,
        bounce_sub_type,
        recipients,
    )

    return {
        "event_type": "bounce",
        "bounce_type": bounce_type,
        "bounce_sub_type": bounce_sub_type,
        "recipients": recipients,
        "message_id": ses_event.get("mail", {}).get("messageId"),
        "timestamp": bounce.get("timestamp"),
    }


def _handle_complaint(ses_event: dict[str, Any]) -> dict[str, Any]:
    """Process SES complaint notification.

    Args:
        ses_event: Parsed SES event

    Returns:
        Summary of the complaint event
    """
    complaint = ses_event.get("complaint", {})
    complaint_type = complaint.get("complaintFeedbackType", "unknown")
    recipients = [r.get("emailAddress", "") for r in complaint.get("complainedRecipients", [])]

    logger.warning(
        "SES complaint: type=%s recipients=%s",
        complaint_type,
        recipients,
    )

    return {
        "event_type": "complaint",
        "complaint_type": complaint_type,
        "recipients": recipients,
        "message_id": ses_event.get("mail", {}).get("messageId"),
        "timestamp": complaint.get("timestamp"),
    }


def _handle_delivery(ses_event: dict[str, Any]) -> dict[str, Any]:
    """Process SES delivery notification.

    Args:
        ses_event: Parsed SES event

    Returns:
        Summary of the delivery event
    """
    delivery = ses_event.get("delivery", {})
    recipients = delivery.get("recipients", [])

    logger.debug("SES delivery confirmed: recipients=%s", recipients)

    return {
        "event_type": "delivery",
        "recipients": recipients,
        "message_id": ses_event.get("mail", {}).get("messageId"),
        "timestamp": delivery.get("timestamp"),
        "processing_time_ms": delivery.get("processingTimeMillis"),
    }


async def handle_sns_notification(body: bytes) -> dict[str, Any]:
    """Process an incoming SNS notification from SES.

    Handles subscription confirmation automatically.
    Parses bounce, complaint, and delivery events.

    Args:
        body: Raw request body

    Returns:
        Dict with event type and details
    """
    message = _parse_sns_message(body)
    message_type = message.get("Type", "")

    # Handle subscription confirmation
    if message_type == "SubscriptionConfirmation":
        confirmed = await _confirm_subscription(message)
        return {"event_type": "subscription_confirmation", "confirmed": confirmed}

    # Handle notification
    if message_type == "Notification":
        ses_event = _parse_ses_event(message.get("Message", ""))
        if not ses_event:
            return {"event_type": "parse_error", "error": "Failed to parse SES event"}

        notification_type = ses_event.get("notificationType", "").lower()

        if notification_type == "bounce":
            return _handle_bounce(ses_event)
        elif notification_type == "complaint":
            return _handle_complaint(ses_event)
        elif notification_type == "delivery":
            return _handle_delivery(ses_event)
        else:
            logger.info("Unknown SES notification type: %s", notification_type)
            return {"event_type": "unknown", "notification_type": notification_type}

    logger.debug("Ignoring SNS message type: %s", message_type)
    return {"event_type": "ignored", "message_type": message_type}


def register_ses_webhook(app: Any) -> None:
    """Register SES webhook endpoint on a FastAPI app.

    POST /webhooks/ses/notifications

    Args:
        app: FastAPI application instance
    """
    try:
        from fastapi import Request
        from fastapi.responses import JSONResponse
    except ImportError:
        logger.debug("FastAPI not available, skipping SES webhook registration")
        return

    @app.post("/webhooks/ses/notifications")  # type: ignore[misc]
    async def ses_webhook(request: Request) -> JSONResponse:
        """Handle incoming SNS notifications from SES."""
        body = await request.body()
        result = await handle_sns_notification(body)

        status_code = 200
        if result.get("event_type") == "parse_error":
            status_code = 400

        return JSONResponse(content=result, status_code=status_code)

    logger.info("SES webhook registered at POST /webhooks/ses/notifications")
