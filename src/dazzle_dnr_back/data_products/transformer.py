"""
Data Product transformer for applying curated stream transforms.

Implements the transform operations defined in DataProductTransform:
- MINIMISE: Remove unnecessary fields, keep only required
- PSEUDONYMISE: Replace identifiers with consistent pseudonyms
- AGGREGATE: Aggregate to remove individual records
- MASK: Partial masking (e.g., email -> j***@example.com)

Design Document: dev_docs/architecture/event_first/EventSystemStabilityRules-v1.md
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from dazzle.core.ir.governance import DataProductTransform

from .curated_topics import CuratedTopicConfig, FieldFilter

logger = logging.getLogger("dazzle.data_products.transformer")


@dataclass
class TransformResult:
    """Result of transforming event data for a curated stream."""

    original_fields: int
    retained_fields: int
    masked_fields: int
    pseudonymised_fields: int
    aggregated: bool
    data: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


class DataProductTransformer:
    """Transforms event payloads for curated data streams.

    Takes an event payload and a CuratedTopicConfig, then:
    1. Filters out denied fields
    2. Applies transforms (mask, pseudonymise, etc.)
    3. Returns transformed payload ready for curated stream

    Example:
        transformer = DataProductTransformer()
        result = transformer.transform(event_payload, config)
        if result.retained_fields > 0:
            publish_to_curated(config.topic_name, result.data)
    """

    def __init__(
        self,
        pseudonym_salt: str = "dazzle-curated",
    ):
        """Initialize transformer.

        Args:
            pseudonym_salt: Salt for pseudonymisation hashes
        """
        self._salt = pseudonym_salt
        # Cache for consistent pseudonyms within a session
        self._pseudonym_cache: dict[str, str] = {}

    def transform(
        self,
        payload: dict[str, Any],
        config: CuratedTopicConfig,
        entity_name: str | None = None,
    ) -> TransformResult:
        """Transform an event payload for a curated stream.

        Args:
            payload: Original event payload
            config: Curated topic configuration
            entity_name: Entity name for field qualification

        Returns:
            TransformResult with transformed data
        """
        original_count = len(payload)
        result_data: dict[str, Any] = {}
        masked_count = 0
        pseudonymised_count = 0

        # Build filter lookup
        filter_lookup: dict[str, FieldFilter] = {}
        for f in config.field_filters:
            if entity_name and f.entity_name != entity_name:
                continue
            filter_lookup[f.field_name] = f

        for field_name, value in payload.items():
            # Check filter
            field_filter = filter_lookup.get(field_name)

            if field_filter:
                if not field_filter.allowed:
                    # Skip denied fields
                    continue

                # Apply transform if specified
                if field_filter.transform:
                    transformed, was_transformed = self._apply_transform(
                        field_name, value, field_filter.transform
                    )
                    result_data[field_name] = transformed
                    if was_transformed:
                        if field_filter.transform == DataProductTransform.MASK:
                            masked_count += 1
                        elif field_filter.transform == DataProductTransform.PSEUDONYMISE:
                            pseudonymised_count += 1
                    continue

            # Check if field is in allowed/denied sets
            qualified = f"{entity_name}.{field_name}" if entity_name else field_name
            if qualified in config.denied_fields:
                continue
            if config.allowed_fields and qualified not in config.allowed_fields:
                # If allow list exists and field not in it, check unqualified
                if field_name not in [f.split(".")[-1] for f in config.allowed_fields]:
                    continue

            # Include field as-is
            result_data[field_name] = value

        return TransformResult(
            original_fields=original_count,
            retained_fields=len(result_data),
            masked_fields=masked_count,
            pseudonymised_fields=pseudonymised_count,
            aggregated=DataProductTransform.AGGREGATE in config.transforms,
            data=result_data,
            metadata={
                "product_name": config.product_name,
                "topic_name": config.topic_name,
            },
        )

    def _apply_transform(
        self,
        field_name: str,
        value: Any,
        transform: DataProductTransform,
    ) -> tuple[Any, bool]:
        """Apply a specific transform to a value.

        Args:
            field_name: Name of the field
            value: Original value
            transform: Transform to apply

        Returns:
            Tuple of (transformed_value, was_transformed)
        """
        if value is None:
            return None, False

        if transform == DataProductTransform.MASK:
            return self._mask_value(field_name, value), True

        if transform == DataProductTransform.PSEUDONYMISE:
            return self._pseudonymise_value(value), True

        if transform == DataProductTransform.MINIMISE:
            # Minimise: truncate long strings, reduce precision
            return self._minimise_value(value), True

        if transform == DataProductTransform.AGGREGATE:
            # Aggregate is handled at stream level, not field level
            return value, False

        return value, False

    def _mask_value(self, field_name: str, value: Any) -> Any:
        """Mask a value based on its type and field name.

        Different masking strategies:
        - Email: j***@example.com
        - Phone: ***-***-1234
        - Card: ****-****-****-1234
        - Generic string: a***z (first/last char)
        - Numbers: rounded or 0
        """
        str_value = str(value)
        field_lower = field_name.lower()

        # Email masking
        if "email" in field_lower or "@" in str_value:
            return self._mask_email(str_value)

        # Phone masking
        if "phone" in field_lower or "mobile" in field_lower:
            return self._mask_phone(str_value)

        # Card number masking
        if "card" in field_lower or "account" in field_lower:
            return self._mask_card(str_value)

        # SSN/National ID masking
        if "ssn" in field_lower or "national" in field_lower:
            return self._mask_ssn(str_value)

        # Generic string masking
        if isinstance(value, str):
            return self._mask_generic_string(str_value)

        # Number masking - return 0 for privacy
        if isinstance(value, int | float):
            return 0

        return "[MASKED]"

    def _mask_email(self, email: str) -> str:
        """Mask an email address: john.doe@example.com -> j***@example.com"""
        if "@" not in email:
            return self._mask_generic_string(email)

        local, domain = email.rsplit("@", 1)
        if len(local) <= 1:
            masked_local = "*"
        else:
            masked_local = f"{local[0]}***"

        return f"{masked_local}@{domain}"

    def _mask_phone(self, phone: str) -> str:
        """Mask a phone number: 555-123-4567 -> ***-***-4567"""
        # Remove non-digits
        digits = re.sub(r"\D", "", phone)
        if len(digits) < 4:
            return "***"
        last_four = digits[-4:]
        return f"***-***-{last_four}"

    def _mask_card(self, card: str) -> str:
        """Mask a card number: 4111-1111-1111-1234 -> ****-****-****-1234"""
        digits = re.sub(r"\D", "", card)
        if len(digits) < 4:
            return "****"
        last_four = digits[-4:]
        return f"****-****-****-{last_four}"

    def _mask_ssn(self, ssn: str) -> str:
        """Mask an SSN: 123-45-6789 -> ***-**-6789"""
        digits = re.sub(r"\D", "", ssn)
        if len(digits) < 4:
            return "***-**-****"
        last_four = digits[-4:]
        return f"***-**-{last_four}"

    def _mask_generic_string(self, value: str) -> str:
        """Mask a generic string: abcdef -> a***f"""
        if len(value) <= 2:
            return "*" * len(value)
        return f"{value[0]}***{value[-1]}"

    def _pseudonymise_value(self, value: Any) -> str:
        """Create a consistent pseudonym for a value.

        Uses SHA256 hash with salt to create reproducible
        pseudonyms that can be used for linking without
        revealing the original value.
        """
        str_value = str(value)

        # Check cache for consistency
        if str_value in self._pseudonym_cache:
            return self._pseudonym_cache[str_value]

        # Create hash-based pseudonym
        to_hash = f"{self._salt}:{str_value}"
        hash_bytes = hashlib.sha256(to_hash.encode()).hexdigest()

        # Create readable pseudonym: PSEUDO_XXXX
        pseudonym = f"PSEUDO_{hash_bytes[:8].upper()}"
        self._pseudonym_cache[str_value] = pseudonym

        return pseudonym

    def _minimise_value(self, value: Any) -> Any:
        """Minimise a value to reduce data footprint.

        - Strings: truncate to 50 chars
        - Floats: round to 2 decimal places
        - Lists: truncate to 10 items with count
        - Dicts: remove nested structure
        """
        if isinstance(value, str):
            if len(value) > 50:
                return value[:47] + "..."
            return value

        if isinstance(value, float):
            return round(value, 2)

        if isinstance(value, list):
            if len(value) > 10:
                return value[:10] + [f"...+{len(value) - 10} more"]
            return value

        if isinstance(value, dict):
            # Flatten to key count only
            return {"_keys": len(value)}

        return value

    def clear_cache(self) -> None:
        """Clear the pseudonym cache.

        Call this between batches or sessions to free memory.
        Pseudonyms will still be consistent within a session
        as long as the same transformer instance is used.
        """
        self._pseudonym_cache.clear()
