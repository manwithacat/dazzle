"""
Email normalizer for DAZZLE.

Converts raw email content into normalized, queryable events.
Extracts structured fields, business references, and safe excerpts.

The normalizer is a consumer that:
1. Reads from office.mail.raw stream
2. Fetches raw content from blob store
3. Parses and extracts structured data
4. Emits to office.mail.normalized stream
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import message_from_bytes
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .blob_store import BlobStore

from dazzle.core.ir.email import (
    BusinessReference,
    EmailAttachmentRef,
    NormalizedMailEvent,
    RawMailEvent,
)

logger = logging.getLogger("dazzle.email.normalizer")


@dataclass
class NormalizationResult:
    """Result of normalizing an email."""

    normalized_event: NormalizedMailEvent
    attachments_stored: list[EmailAttachmentRef]
    extraction_metadata: dict[str, Any] = field(default_factory=dict)


class EmailNormalizer:
    """Normalizes raw emails into structured events.

    Performs:
    - Header parsing (from, to, subject, etc.)
    - Body extraction and redaction
    - Attachment handling (store to blob, create refs)
    - Business reference extraction (invoice #, ticket ID, etc.)
    - Language detection
    - Classification (optional, can be enhanced by LLM)
    """

    # Common business reference patterns
    BUSINESS_REF_PATTERNS = [
        # Invoice numbers
        (r"(?:invoice|inv)[#:\s]*([A-Z0-9-]+)", "invoice_ref"),
        # Ticket/case IDs
        (r"(?:ticket|case|issue)[#:\s]*([A-Z0-9-]+)", "ticket_id"),
        # Order numbers
        (r"(?:order|ord)[#:\s]*([A-Z0-9-]+)", "order_id"),
        # Reference numbers
        (r"(?:ref|reference)[#:\s]*([A-Z0-9-]+)", "reference"),
        # PO numbers
        (r"(?:po|purchase order)[#:\s]*([A-Z0-9-]+)", "po_number"),
    ]

    # Patterns for redaction (PII, etc.)
    REDACT_PATTERNS = [
        # Credit card numbers (basic pattern)
        (r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "[CARD]"),
        # SSN-like patterns
        (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),
        # Phone numbers (basic)
        (r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[PHONE]"),
    ]

    def __init__(
        self,
        blob_store: BlobStore,
        max_excerpt_length: int = 500,
        redact_pii: bool = True,
    ):
        """Initialize normalizer.

        Args:
            blob_store: Blob store for attachments
            max_excerpt_length: Maximum body excerpt length
            redact_pii: Whether to redact PII patterns
        """
        self._blob_store = blob_store
        self._max_excerpt = max_excerpt_length
        self._redact_pii = redact_pii

    async def normalize(self, raw_event: RawMailEvent) -> NormalizationResult:
        """Normalize a raw email event.

        Args:
            raw_event: Raw mail event with blob pointer

        Returns:
            NormalizationResult with normalized event and metadata
        """
        # Fetch raw content
        raw_content = await self._blob_store.retrieve(raw_event.raw_pointer)
        if not raw_content:
            raise ValueError(f"Raw content not found: {raw_event.raw_pointer}")

        # Parse email
        msg = message_from_bytes(raw_content)

        # Extract body
        body_text, has_html = self._extract_body(msg)
        body_excerpt = self._create_excerpt(body_text)

        # Redact if enabled
        if self._redact_pii:
            body_excerpt = self._redact_sensitive(body_excerpt)

        # Extract business references
        business_refs = self._extract_business_refs(body_text)

        # Store attachments and create refs
        attachment_refs = await self._process_attachments(msg, raw_event.mail_id)

        # Parse from address
        from_name, from_addr = parseaddr(raw_event.from_address)
        from_domain = from_addr.split("@")[1] if "@" in from_addr else ""

        # Detect language (basic implementation)
        language = self._detect_language(body_text)

        # Create normalized event
        normalized = NormalizedMailEvent(
            mail_id=raw_event.mail_id,
            raw_pointer=raw_event.raw_pointer,
            received_at=raw_event.received_at,
            normalized_at=datetime.now(UTC),
            from_address=from_addr,
            from_domain=from_domain,
            from_display_name=from_name if from_name else None,
            to_count=len(raw_event.to_addresses),
            cc_count=len(raw_event.cc_addresses),
            subject_redacted=self._redact_sensitive(raw_event.subject or "") if self._redact_pii else (raw_event.subject or ""),
            body_excerpt_redacted=body_excerpt,
            body_length=len(body_text),
            has_html=has_html,
            language=language,
            business_refs=business_refs,
            attachments=attachment_refs,
            classification=None,  # Can be set by LLM later
            priority=None,
            tenant_id=raw_event.tenant_id,
            customer_id=None,  # Can be linked later
        )

        return NormalizationResult(
            normalized_event=normalized,
            attachments_stored=attachment_refs,
            extraction_metadata={
                "body_length": len(body_text),
                "has_html": has_html,
                "attachment_count": len(attachment_refs),
                "business_refs_count": len(business_refs),
            },
        )

    def _extract_body(self, msg: Message) -> tuple[str, bool]:
        """Extract body text from email message.

        Returns:
            Tuple of (text_body, has_html)
        """
        text_body = ""
        has_html = False

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = part.get("Content-Disposition", "")

                # Skip attachments
                if "attachment" in content_disposition:
                    continue

                if content_type == "text/plain" and not text_body:
                    payload = part.get_payload(decode=True)
                    if payload and isinstance(payload, bytes):
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            text_body = payload.decode(charset, errors="replace")
                        except LookupError:
                            text_body = payload.decode("utf-8", errors="replace")

                elif content_type == "text/html":
                    has_html = True
                    # If no plain text, extract from HTML
                    if not text_body:
                        payload = part.get_payload(decode=True)
                        if payload and isinstance(payload, bytes):
                            charset = part.get_content_charset() or "utf-8"
                            try:
                                html = payload.decode(charset, errors="replace")
                            except LookupError:
                                html = payload.decode("utf-8", errors="replace")
                            text_body = self._strip_html(html)
        else:
            payload = msg.get_payload(decode=True)
            if payload and isinstance(payload, bytes):
                charset = msg.get_content_charset() or "utf-8"
                try:
                    text_body = payload.decode(charset, errors="replace")
                except LookupError:
                    text_body = payload.decode("utf-8", errors="replace")

                if msg.get_content_type() == "text/html":
                    has_html = True
                    text_body = self._strip_html(text_body)

        return text_body, has_html

    def _strip_html(self, html: str) -> str:
        """Strip HTML tags for plain text extraction."""
        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove tags
        html = re.sub(r"<[^>]+>", " ", html)
        # Decode HTML entities
        html = html.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        # Normalize whitespace
        html = re.sub(r"\s+", " ", html).strip()
        return html

    def _create_excerpt(self, text: str) -> str:
        """Create a safe excerpt from body text."""
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) <= self._max_excerpt:
            return text

        # Truncate at word boundary
        excerpt = text[: self._max_excerpt]
        last_space = excerpt.rfind(" ")
        if last_space > self._max_excerpt * 0.8:
            excerpt = excerpt[:last_space]

        return excerpt + "..."

    def _redact_sensitive(self, text: str) -> str:
        """Redact sensitive patterns from text."""
        for pattern, replacement in self.REDACT_PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def _extract_business_refs(self, text: str) -> list[BusinessReference]:
        """Extract business references from text."""
        refs: list[BusinessReference] = []
        seen: set[tuple[str, str]] = set()

        for pattern, ref_type in self.BUSINESS_REF_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group(1).upper()
                key = (ref_type, value)

                if key not in seen:
                    seen.add(key)
                    refs.append(
                        BusinessReference(
                            ref_type=ref_type,
                            ref_value=value,
                            confidence=0.9,  # Pattern-based extraction
                        )
                    )

        return refs

    async def _process_attachments(
        self,
        msg: Message,
        mail_id: str,
    ) -> list[EmailAttachmentRef]:
        """Process and store attachments.

        Returns list of attachment references (pointers to blob store).
        """
        refs: list[EmailAttachmentRef] = []

        if not msg.is_multipart():
            return refs

        for part in msg.walk():
            content_disposition = part.get("Content-Disposition", "")
            if "attachment" not in content_disposition:
                continue

            filename = part.get_filename()
            if not filename:
                filename = "attachment"

            # Decode filename if needed
            if filename:
                decoded = decode_header(filename)
                if decoded:
                    filename_part, charset = decoded[0]
                    if isinstance(filename_part, bytes):
                        filename = filename_part.decode(charset or "utf-8", errors="replace")
                    else:
                        filename = filename_part

            # Get content
            payload = part.get_payload(decode=True)
            if not payload or not isinstance(payload, bytes):
                continue

            content_type = part.get_content_type() or "application/octet-stream"

            # Store to blob
            blob_meta = await self._blob_store.store(
                content=payload,
                content_type=content_type,
                prefix="attachments",
                metadata={
                    "mail_id": mail_id,
                    "original_filename": filename,
                },
            )

            # Redact filename if needed
            name_redacted = self._redact_sensitive(filename) if self._redact_pii else filename

            refs.append(
                EmailAttachmentRef(
                    name_redacted=name_redacted,
                    mime_type=content_type,
                    size_bytes=blob_meta.size_bytes,
                    pointer=blob_meta.pointer,
                    sha256=blob_meta.sha256,
                )
            )

        return refs

    def _detect_language(self, text: str) -> str | None:
        """Detect language of text.

        Basic implementation using common word patterns.
        Can be enhanced with langdetect or similar library.
        """
        if not text or len(text) < 20:
            return None

        # Simple heuristic based on common words
        text_lower = text.lower()

        # English indicators
        english_words = ["the", "is", "are", "was", "were", "have", "has", "been"]
        english_score = sum(1 for w in english_words if f" {w} " in text_lower)

        # Spanish indicators
        spanish_words = ["el", "la", "los", "las", "es", "son", "está", "están"]
        spanish_score = sum(1 for w in spanish_words if f" {w} " in text_lower)

        # French indicators
        french_words = ["le", "la", "les", "est", "sont", "être", "avoir"]
        french_score = sum(1 for w in french_words if f" {w} " in text_lower)

        scores = [
            ("en", english_score),
            ("es", spanish_score),
            ("fr", french_score),
        ]

        best = max(scores, key=lambda x: x[1])
        if best[1] >= 2:
            return best[0]

        return None
