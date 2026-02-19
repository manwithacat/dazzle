"""
Email channel adapters for DAZZLE messaging.

Provides adapters for:
- Mailpit (local development)
- File-based (fallback, saves to disk)
"""

from __future__ import annotations

import json
import logging
import smtplib
import time
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .base import EmailAdapter, SendResult, SendStatus

if TYPE_CHECKING:
    from ..detection import DetectionResult
    from ..outbox import OutboxMessage

logger = logging.getLogger("dazzle.channels.adapters.email")


class MailpitAdapter(EmailAdapter):
    """Adapter for Mailpit email testing server.

    Sends emails via SMTP to Mailpit, which captures them for inspection.
    Perfect for local development and testing.
    """

    def __init__(self, detection_result: DetectionResult):
        super().__init__(detection_result)
        self._smtp_host = "localhost"
        self._smtp_port = 1025

        # Parse connection URL for host/port
        if detection_result.connection_url:
            url = detection_result.connection_url
            if url.startswith("smtp://"):
                url = url[7:]
            if ":" in url:
                host, port_str = url.rsplit(":", 1)
                self._smtp_host = host
                try:
                    self._smtp_port = int(port_str)
                except ValueError:
                    pass

    @property
    def provider_name(self) -> str:
        return "mailpit"

    async def initialize(self) -> None:
        """Initialize the Mailpit adapter."""
        await super().initialize()
        logger.info(f"Mailpit adapter initialized (smtp://{self._smtp_host}:{self._smtp_port})")

    async def send(self, message: OutboxMessage) -> SendResult:
        """Send email via Mailpit SMTP.

        Args:
            message: Outbox message to send

        Returns:
            SendResult with status
        """
        email_data = self.build_email(message)

        try:
            start = time.monotonic()

            # Build MIME message
            msg = MIMEMultipart("alternative")
            msg["From"] = email_data["from"]
            msg["To"] = email_data["to"]
            msg["Subject"] = email_data["subject"]

            if email_data.get("reply_to"):
                msg["Reply-To"] = email_data["reply_to"]

            if email_data.get("cc"):
                msg["Cc"] = ", ".join(email_data["cc"])

            # Add body parts
            if email_data.get("body"):
                msg.attach(MIMEText(email_data["body"], "plain"))

            if email_data.get("html_body"):
                msg.attach(MIMEText(email_data["html_body"], "html"))

            # Send via SMTP
            with smtplib.SMTP(self._smtp_host, self._smtp_port) as smtp:
                recipients = [email_data["to"]]
                if email_data.get("cc"):
                    recipients.extend(email_data["cc"])
                if email_data.get("bcc"):
                    recipients.extend(email_data["bcc"])

                smtp.sendmail(email_data["from"], recipients, msg.as_string())

            latency = (time.monotonic() - start) * 1000

            logger.info(f"Email sent via Mailpit: {email_data['to']} - {email_data['subject']}")

            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=message.id,
                latency_ms=latency,
                provider_response={"smtp_host": self._smtp_host, "smtp_port": self._smtp_port},
            )

        except smtplib.SMTPException as e:
            logger.error(f"Mailpit SMTP error: {e}")
            return SendResult(
                status=SendStatus.FAILED,
                error=str(e),
            )
        except ConnectionRefusedError:
            logger.error(f"Cannot connect to Mailpit at {self._smtp_host}:{self._smtp_port}")
            return SendResult(
                status=SendStatus.FAILED,
                error=f"Connection refused to {self._smtp_host}:{self._smtp_port}",
            )
        except Exception as e:
            logger.error(f"Unexpected error sending via Mailpit: {e}")
            return SendResult(
                status=SendStatus.FAILED,
                error=str(e),
            )

    async def health_check(self) -> bool:
        """Check if Mailpit is accessible."""
        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=5) as smtp:
                smtp.noop()
            return True
        except Exception:
            logger.debug("Health check failed", exc_info=True)
            return False


class SESAdapter(EmailAdapter):
    """Adapter for Amazon SES v2 email service.

    Sends emails via SES v2 API with support for transactional and bulk sends.
    Handles to, cc, bcc, reply_to, and attachments.
    """

    def __init__(self, detection_result: DetectionResult):
        super().__init__(detection_result)
        self._from_address = detection_result.metadata.get("from_address", "noreply@example.com")
        self._config_set = detection_result.metadata.get("configuration_set")
        self._ses_region = detection_result.metadata.get("region", "us-east-1")

    @property
    def provider_name(self) -> str:
        return "ses"

    async def initialize(self) -> None:
        """Initialize the SES adapter."""
        await super().initialize()
        logger.info(
            f"SES adapter initialized (region={self._ses_region}, from={self._from_address})"
        )

    def _get_ses_client_kwargs(self) -> dict[str, Any]:
        """Get kwargs for creating an SES v2 client."""
        from dazzle_back.runtime.aws_config import get_aws_config

        config = get_aws_config()
        kwargs = config.to_boto3_kwargs()
        kwargs["region_name"] = self._ses_region
        return kwargs

    async def send(self, message: OutboxMessage) -> SendResult:
        """Send email via SES v2 API.

        Args:
            message: Outbox message to send

        Returns:
            SendResult with status
        """
        try:
            from dazzle_back.runtime.aws_config import get_aioboto3_session
        except ImportError:
            return SendResult(
                status=SendStatus.FAILED,
                error="aioboto3 required for SES. Install with: pip install dazzle-dsl[aws]",
            )

        email_data = self.build_email(message)

        try:
            start = time.monotonic()
            session = get_aioboto3_session()
            kwargs = self._get_ses_client_kwargs()

            async with session.client("sesv2", **kwargs) as ses:
                # Build destination
                destination: dict[str, Any] = {"ToAddresses": [email_data["to"]]}
                if email_data.get("cc"):
                    destination["CcAddresses"] = email_data["cc"]
                if email_data.get("bcc"):
                    destination["BccAddresses"] = email_data["bcc"]

                # Build email content
                body: dict[str, Any] = {}
                if email_data.get("body"):
                    body["Text"] = {"Data": email_data["body"], "Charset": "UTF-8"}
                if email_data.get("html_body"):
                    body["Html"] = {"Data": email_data["html_body"], "Charset": "UTF-8"}

                send_kwargs: dict[str, Any] = {
                    "FromEmailAddress": email_data.get("from", self._from_address),
                    "Destination": destination,
                    "Content": {
                        "Simple": {
                            "Subject": {
                                "Data": email_data["subject"],
                                "Charset": "UTF-8",
                            },
                            "Body": body,
                        }
                    },
                }

                if email_data.get("reply_to"):
                    send_kwargs["ReplyToAddresses"] = [email_data["reply_to"]]

                if self._config_set:
                    send_kwargs["ConfigurationSetName"] = self._config_set

                response = await ses.send_email(**send_kwargs)

            latency = (time.monotonic() - start) * 1000
            ses_message_id = response.get("MessageId", "")

            logger.info(f"Email sent via SES: {email_data['to']} - {email_data['subject']}")

            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=ses_message_id,
                latency_ms=latency,
                provider_response={"ses_message_id": ses_message_id},
            )

        except Exception as e:
            logger.error(f"SES send error: {e}")
            error_str = str(e)

            # Check for throttling
            if "Throttling" in error_str or "TooManyRequests" in error_str:
                return SendResult(
                    status=SendStatus.RATE_LIMITED,
                    error=error_str,
                )

            return SendResult(
                status=SendStatus.FAILED,
                error=error_str,
            )

    async def send_bulk(self, messages: list[OutboxMessage]) -> list[SendResult]:
        """Send multiple emails via SES v2 bulk API.

        Groups messages into batches of 50 (SES limit per call).

        Args:
            messages: List of outbox messages to send

        Returns:
            List of SendResult, one per message
        """
        results: list[SendResult] = []
        batch_size = 50

        for i in range(0, len(messages), batch_size):
            batch = messages[i : i + batch_size]
            batch_results = await self._send_batch(batch)
            results.extend(batch_results)

        return results

    async def _send_batch(self, messages: list[OutboxMessage]) -> list[SendResult]:
        """Send a batch of messages via SES bulk API."""
        # Fall back to individual sends for simplicity
        # SES v2 SendBulkEmail requires templates; for non-templated we send individually
        results: list[SendResult] = []
        for msg in messages:
            result = await self.send(msg)
            results.append(result)
        return results

    async def health_check(self) -> bool:
        """Check if SES is accessible by calling get_account."""
        try:
            from dazzle_back.runtime.aws_config import get_aioboto3_session

            session = get_aioboto3_session()
            kwargs = self._get_ses_client_kwargs()

            async with session.client("sesv2", **kwargs) as ses:
                response = await ses.get_account()
                # Check sending is not paused
                return bool(response.get("SendingEnabled", True))

        except Exception:
            logger.debug("SES health check failed", exc_info=True)
            return False


class FileEmailAdapter(EmailAdapter):
    """File-based email adapter (fallback).

    Saves emails to disk in .eml format for inspection.
    Always available, useful when no email server is configured.
    """

    def __init__(self, detection_result: DetectionResult):
        super().__init__(detection_result)
        self._mail_dir = Path.cwd() / ".dazzle" / "mail"

        # Parse directory from connection URL
        if detection_result.connection_url:
            url = detection_result.connection_url
            if url.startswith("file://"):
                self._mail_dir = Path(url[7:])

    @property
    def provider_name(self) -> str:
        return "file"

    async def initialize(self) -> None:
        """Initialize the file email adapter."""
        await super().initialize()
        self._mail_dir.mkdir(parents=True, exist_ok=True)
        (self._mail_dir / "messages").mkdir(exist_ok=True)
        logger.info(f"File email adapter initialized (directory: {self._mail_dir})")

    async def send(self, message: OutboxMessage) -> SendResult:
        """Save email to file.

        Args:
            message: Outbox message to send

        Returns:
            SendResult with status
        """
        email_data = self.build_email(message)

        try:
            start = time.monotonic()

            # Build MIME message
            msg = MIMEMultipart("alternative")
            msg["From"] = email_data["from"]
            msg["To"] = email_data["to"]
            msg["Subject"] = email_data["subject"]
            msg["Date"] = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")
            msg["Message-ID"] = f"<{message.id}@dazzle.local>"

            if email_data.get("reply_to"):
                msg["Reply-To"] = email_data["reply_to"]

            if email_data.get("body"):
                msg.attach(MIMEText(email_data["body"], "plain"))

            if email_data.get("html_body"):
                msg.attach(MIMEText(email_data["html_body"], "html"))

            # Generate filename
            timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
            safe_id = message.id[:8]
            filename = f"{timestamp}_{safe_id}.eml"

            # Save to file
            filepath = self._mail_dir / "messages" / filename
            filepath.write_text(msg.as_string())

            # Update index
            await self._update_index(message, email_data, filename)

            latency = (time.monotonic() - start) * 1000

            logger.info(f"Email saved to file: {filepath}")

            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=message.id,
                latency_ms=latency,
                provider_response={"filepath": str(filepath)},
            )

        except Exception as e:
            logger.error(f"Error saving email to file: {e}")
            return SendResult(
                status=SendStatus.FAILED,
                error=str(e),
            )

    async def _update_index(
        self,
        message: OutboxMessage,
        email_data: dict[str, Any],
        filename: str,
    ) -> None:
        """Update the email index file."""
        index_path = self._mail_dir / "index.json"

        # Load existing index
        if index_path.exists():
            try:
                index = json.loads(index_path.read_text())
            except json.JSONDecodeError:
                index = {"messages": []}
        else:
            index = {"messages": []}

        # Add new entry
        index["messages"].insert(
            0,
            {
                "id": message.id,
                "filename": filename,
                "to": email_data["to"],
                "from": email_data["from"],
                "subject": email_data["subject"],
                "timestamp": datetime.now(UTC).isoformat(),
                "channel": message.channel_name,
                "operation": message.operation_name,
            },
        )

        # Keep only last 1000 messages in index
        index["messages"] = index["messages"][:1000]

        # Save index
        index_path.write_text(json.dumps(index, indent=2))

    async def health_check(self) -> bool:
        """File adapter is always healthy."""
        return True

    async def get_recent_emails(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent emails from the index.

        Args:
            limit: Maximum emails to return

        Returns:
            List of email summaries
        """
        index_path = self._mail_dir / "index.json"

        if not index_path.exists():
            return []

        try:
            index = json.loads(index_path.read_text())
            messages: list[dict[str, Any]] = index.get("messages", [])[:limit]
            return messages
        except json.JSONDecodeError:
            return []

    async def get_email_content(self, message_id: str) -> str | None:
        """Get full email content by ID.

        Args:
            message_id: Message ID

        Returns:
            Email content as string or None if not found
        """
        index_path = self._mail_dir / "index.json"

        if not index_path.exists():
            return None

        try:
            index = json.loads(index_path.read_text())
            for entry in index.get("messages", []):
                if entry["id"] == message_id:
                    filepath = self._mail_dir / "messages" / entry["filename"]
                    if filepath.exists():
                        content: str = filepath.read_text()
                        return content
        except (json.JSONDecodeError, KeyError):
            pass

        return None
