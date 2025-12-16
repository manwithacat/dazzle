"""
Inbound email adapters for DAZZLE.

Handles receiving emails from various sources and converting them
to raw mail events.

Implementations:
- MailpitInboundAdapter: Polls Mailpit HTTP API for dev
- SMTPInboundAdapter: SMTP server for edge ingestion (future)
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from email import message_from_bytes
from email.message import Message
from email.utils import parseaddr
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .blob_store import BlobStore

logger = logging.getLogger("dazzle.email.inbound")


@dataclass
class RawMailArtifact:
    """Result of receiving and storing raw mail.

    Contains all data needed to create a RawMailEvent.
    """

    mail_id: str
    message_id: str | None
    received_at: datetime

    # Headers
    from_address: str
    to_addresses: list[str]
    cc_addresses: list[str]
    subject: str | None

    # Blob info
    raw_pointer: str
    raw_sha256: str
    size_bytes: int

    # Attachments
    attachments_present: bool
    attachment_count: int

    # Provider info
    provider: str
    provider_message_id: str | None = None


class InboundMailAdapter(ABC):
    """Abstract interface for inbound mail adapters.

    Adapters are responsible for:
    1. Receiving/fetching mail from a source
    2. Storing raw content to blob store
    3. Returning RawMailArtifact for event creation
    """

    def __init__(self, blob_store: BlobStore):
        self._blob_store = blob_store

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of this provider."""
        ...

    @abstractmethod
    async def fetch_new_messages(self, limit: int = 100) -> list[RawMailArtifact]:
        """Fetch new messages from the source.

        Args:
            limit: Maximum messages to fetch

        Returns:
            List of RawMailArtifact for each message
        """
        ...

    @abstractmethod
    async def mark_processed(self, mail_id: str) -> None:
        """Mark a message as processed.

        Args:
            mail_id: Internal mail ID
        """
        ...

    async def _store_and_create_artifact(
        self,
        raw_content: bytes,
        provider_message_id: str | None = None,
    ) -> RawMailArtifact:
        """Store raw content and parse headers to create artifact.

        Args:
            raw_content: Raw email bytes
            provider_message_id: ID from the provider

        Returns:
            RawMailArtifact ready for event creation
        """
        # Parse email
        msg = message_from_bytes(raw_content)

        # Extract headers
        from_addr = self._extract_address(msg.get("From", ""))
        to_addrs = self._extract_address_list(msg.get("To", ""))
        cc_addrs = self._extract_address_list(msg.get("Cc", ""))
        subject = msg.get("Subject")
        message_id = msg.get("Message-ID")

        # Count attachments
        attachment_count = self._count_attachments(msg)

        # Store to blob
        blob_meta = await self._blob_store.store(
            content=raw_content,
            content_type="message/rfc822",
            prefix="raw",
            metadata={
                "from": from_addr,
                "subject": subject or "",
                "provider": self.provider_name,
            },
        )

        return RawMailArtifact(
            mail_id=str(uuid.uuid4()),
            message_id=message_id,
            received_at=datetime.now(UTC),
            from_address=from_addr,
            to_addresses=to_addrs,
            cc_addresses=cc_addrs,
            subject=subject,
            raw_pointer=blob_meta.pointer,
            raw_sha256=blob_meta.sha256,
            size_bytes=blob_meta.size_bytes,
            attachments_present=attachment_count > 0,
            attachment_count=attachment_count,
            provider=self.provider_name,
            provider_message_id=provider_message_id,
        )

    def _extract_address(self, header: str) -> str:
        """Extract email address from header value."""
        if not header:
            return ""
        _, addr = parseaddr(header)
        return addr

    def _extract_address_list(self, header: str) -> list[str]:
        """Extract list of addresses from header."""
        if not header:
            return []
        # Simple split - could use email.utils.getaddresses for complex cases
        addresses = []
        for part in header.split(","):
            addr = self._extract_address(part.strip())
            if addr:
                addresses.append(addr)
        return addresses

    def _count_attachments(self, msg: Message) -> int:
        """Count attachments in a message."""
        count = 0
        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = part.get("Content-Disposition", "")
                if "attachment" in content_disposition:
                    count += 1
        return count


class MailpitInboundAdapter(InboundMailAdapter):
    """Inbound adapter that polls Mailpit HTTP API.

    Mailpit provides a REST API for accessing received messages.
    This adapter polls that API and fetches new messages.

    For development and testing use.
    """

    def __init__(
        self,
        blob_store: BlobStore,
        http_url: str = "http://localhost:8025",
    ):
        """Initialize Mailpit inbound adapter.

        Args:
            blob_store: Blob store for raw content
            http_url: Mailpit HTTP API URL
        """
        super().__init__(blob_store)
        self._http_url = http_url.rstrip("/")
        self._processed_ids: set[str] = set()
        self._last_poll: datetime | None = None

    @property
    def provider_name(self) -> str:
        return "mailpit"

    async def fetch_new_messages(self, limit: int = 100) -> list[RawMailArtifact]:
        """Fetch new messages from Mailpit.

        Uses Mailpit's messages API to list messages, then fetches
        raw content for unprocessed ones.

        Args:
            limit: Maximum messages to fetch

        Returns:
            List of new RawMailArtifact
        """
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not installed, cannot poll Mailpit")
            return []

        artifacts = []

        try:
            async with httpx.AsyncClient() as client:
                # List messages
                response = await client.get(
                    f"{self._http_url}/api/v1/messages",
                    params={"limit": limit},
                    timeout=10.0,
                )

                if response.status_code != 200:
                    logger.warning(f"Mailpit API error: {response.status_code}")
                    return []

                data = response.json()
                messages = data.get("messages", [])

                for msg_summary in messages:
                    msg_id = msg_summary.get("ID")
                    if not msg_id or msg_id in self._processed_ids:
                        continue

                    # Fetch raw message
                    raw_response = await client.get(
                        f"{self._http_url}/api/v1/message/{msg_id}/raw",
                        timeout=30.0,
                    )

                    if raw_response.status_code != 200:
                        logger.warning(f"Failed to fetch raw message {msg_id}")
                        continue

                    raw_content = raw_response.content

                    # Create artifact
                    artifact = await self._store_and_create_artifact(
                        raw_content=raw_content,
                        provider_message_id=msg_id,
                    )
                    artifacts.append(artifact)

                    logger.info(
                        f"Fetched mail from Mailpit: {artifact.from_address} -> {artifact.to_addresses}"
                    )

                self._last_poll = datetime.now(UTC)

        except Exception as e:
            logger.error(f"Error polling Mailpit: {e}")

        return artifacts

    async def mark_processed(self, mail_id: str) -> None:
        """Mark message as processed (just track locally)."""
        # We track by provider_message_id in our processed set
        self._processed_ids.add(mail_id)

    async def health_check(self) -> bool:
        """Check if Mailpit is accessible."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._http_url}/api/v1/messages",
                    params={"limit": 1},
                    timeout=5.0,
                )
                return response.status_code == 200
        except Exception:
            return False


class SMTPInboundAdapter(InboundMailAdapter):
    """SMTP server adapter for edge ingestion.

    Runs a minimal SMTP server that receives mail and emits events.
    For production use with SES or direct SMTP routing.

    TODO: Implement in Phase F.2
    """

    def __init__(
        self,
        blob_store: BlobStore,
        host: str = "0.0.0.0",
        port: int = 2525,
    ):
        super().__init__(blob_store)
        self._host = host
        self._port = port

    @property
    def provider_name(self) -> str:
        return "smtp_edge"

    async def fetch_new_messages(self, limit: int = 100) -> list[RawMailArtifact]:
        """Not applicable - SMTP adapter receives messages via server."""
        raise NotImplementedError("SMTP adapter receives via server, not polling")

    async def mark_processed(self, mail_id: str) -> None:
        """No-op for SMTP adapter."""
        pass

    async def start_server(self) -> None:
        """Start SMTP server.

        TODO: Implement using aiosmtpd
        """
        raise NotImplementedError("SMTP server not yet implemented")
