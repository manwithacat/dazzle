"""
Curated topic generation for Data Products.

Generates curated topic configurations from DataProductSpec definitions.
Topics are placed in a separate namespace (e.g., "curated.analytics_v1")
with field filtering based on data classifications.

Design Document: dev_docs/architecture/event_first/EventSystemStabilityRules-v1.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dazzle.core.ir.governance import (
    DataClassification,
    DataProductSpec,
    DataProductTransform,
)

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec, EntitySpec

logger = logging.getLogger("dazzle.data_products.curated_topics")


@dataclass
class FieldFilter:
    """Filter configuration for a field in a curated topic.

    Determines whether a field should be included and what
    transform to apply.
    """

    field_name: str
    entity_name: str
    classification: DataClassification
    allowed: bool
    transform: DataProductTransform | None = None


@dataclass
class CuratedTopicConfig:
    """Configuration for a curated data product topic.

    Contains all information needed to set up the curated stream:
    - Topic naming in curated namespace
    - Field filters (include/exclude based on classification)
    - Transforms to apply
    - Cross-tenant settings
    """

    # Topic identification
    product_name: str
    topic_name: str  # Full topic name (e.g., "curated.analytics_v1")
    source_topics: list[str] = field(default_factory=list)

    # Field filtering
    field_filters: list[FieldFilter] = field(default_factory=list)
    allowed_fields: set[str] = field(default_factory=set)
    denied_fields: set[str] = field(default_factory=set)

    # Transforms
    transforms: list[DataProductTransform] = field(default_factory=list)

    # Cross-tenant
    cross_tenant: bool = False

    # Metadata
    retention: str | None = None
    refresh: str = "realtime"
    description: str | None = None


class CuratedTopicGenerator:
    """Generates curated topic configurations from DataProductSpec.

    Takes a DataProductSpec and the full AppSpec, then produces
    CuratedTopicConfig objects that can be used to:
    - Create curated topic subscriptions
    - Apply field filtering to events
    - Transform data before publishing to curated stream

    Example:
        generator = CuratedTopicGenerator(appspec)
        for config in generator.generate():
            print(f"Curated topic: {config.topic_name}")
            for f in config.allowed_fields:
                print(f"  - {f}")
    """

    def __init__(
        self,
        appspec: AppSpec,
        namespace: str = "curated",
    ):
        """Initialize the generator.

        Args:
            appspec: Full application specification
            namespace: Namespace prefix for curated topics
        """
        self._appspec = appspec
        self._namespace = namespace

        # Build classification lookup from policies
        self._field_classifications: dict[tuple[str, str], DataClassification] = {}
        if appspec.policies:
            for cls in appspec.policies.classifications:
                key = (cls.entity, cls.field)
                self._field_classifications[key] = cls.classification

    def generate(self) -> list[CuratedTopicConfig]:
        """Generate curated topic configs for all data products.

        Returns:
            List of CuratedTopicConfig objects
        """
        if not self._appspec.data_products:
            return []

        configs: list[CuratedTopicConfig] = []
        namespace = self._appspec.data_products.default_namespace or self._namespace

        for product in self._appspec.data_products.products:
            config = self._generate_for_product(product, namespace)
            configs.append(config)

        return configs

    def _generate_for_product(
        self,
        product: DataProductSpec,
        namespace: str,
    ) -> CuratedTopicConfig:
        """Generate config for a single data product.

        Args:
            product: Data product specification
            namespace: Topic namespace

        Returns:
            CuratedTopicConfig for this product
        """
        # Determine topic name
        topic_name = product.output_topic or f"{namespace}.{product.name}"

        # Build field filters from source entities
        field_filters: list[FieldFilter] = []
        allowed_fields: set[str] = set()
        denied_fields: set[str] = set()

        for entity_name in product.source_entities:
            entity = self._find_entity(entity_name)
            if not entity:
                logger.warning(f"Entity not found: {entity_name}")
                continue

            # Check each field against allow/deny classifications
            for field_spec in entity.fields:
                key = (entity_name, field_spec.name)
                classification = self._field_classifications.get(
                    key, DataClassification.UNCLASSIFIED
                )

                # Determine if field is allowed
                allowed = self._is_field_allowed(
                    classification,
                    product.allow_classifications,
                    product.deny_classifications,
                )

                # Determine transform to apply
                transform = self._get_transform_for_field(classification, product.transforms)

                field_filter = FieldFilter(
                    field_name=field_spec.name,
                    entity_name=entity_name,
                    classification=classification,
                    allowed=allowed,
                    transform=transform,
                )
                field_filters.append(field_filter)

                qualified_name = f"{entity_name}.{field_spec.name}"
                if allowed:
                    allowed_fields.add(qualified_name)
                else:
                    denied_fields.add(qualified_name)

        # Build source topics from source entities
        source_topics = [f"app.{entity_name}" for entity_name in product.source_entities]

        # Add source streams directly
        source_topics.extend(product.source_streams)

        return CuratedTopicConfig(
            product_name=product.name,
            topic_name=topic_name,
            source_topics=source_topics,
            field_filters=field_filters,
            allowed_fields=allowed_fields,
            denied_fields=denied_fields,
            transforms=product.transforms,
            cross_tenant=product.cross_tenant,
            retention=product.retention,
            refresh=product.refresh,
            description=product.description,
        )

    def _find_entity(self, name: str) -> EntitySpec | None:
        """Find an entity by name in the AppSpec."""
        return self._appspec.domain.get_entity(name)

    def _is_field_allowed(
        self,
        classification: DataClassification,
        allow_list: list[DataClassification],
        deny_list: list[DataClassification],
    ) -> bool:
        """Determine if a field is allowed based on classifications.

        Rules:
        1. If deny_list contains the classification, field is denied
        2. If allow_list is non-empty, field must be in allow_list
        3. Otherwise, field is allowed (default)

        Args:
            classification: Field's classification
            allow_list: Classifications to explicitly allow
            deny_list: Classifications to explicitly deny

        Returns:
            True if field is allowed
        """
        # Deny takes precedence
        if classification in deny_list:
            return False

        # If allow list specified, must be in it
        if allow_list:
            return classification in allow_list

        # Default: allow
        return True

    def _get_transform_for_field(
        self,
        classification: DataClassification,
        transforms: list[DataProductTransform],
    ) -> DataProductTransform | None:
        """Determine which transform to apply to a field.

        Maps classifications to appropriate transforms:
        - PII_DIRECT: pseudonymise or mask
        - PII_INDIRECT: minimise or mask
        - PII_SENSITIVE: aggregate (if available)
        - FINANCIAL_TXN: none (usually allowed)
        - FINANCIAL_ACCOUNT: mask

        Args:
            classification: Field's classification
            transforms: Available transforms

        Returns:
            Transform to apply, or None
        """
        if not transforms:
            return None

        # Map classifications to preferred transforms
        preferred: dict[DataClassification, list[DataProductTransform]] = {
            DataClassification.PII_DIRECT: [
                DataProductTransform.PSEUDONYMISE,
                DataProductTransform.MASK,
            ],
            DataClassification.PII_INDIRECT: [
                DataProductTransform.MINIMISE,
                DataProductTransform.MASK,
            ],
            DataClassification.PII_SENSITIVE: [
                DataProductTransform.AGGREGATE,
                DataProductTransform.PSEUDONYMISE,
            ],
            DataClassification.FINANCIAL_ACCOUNT: [
                DataProductTransform.MASK,
            ],
        }

        prefs = preferred.get(classification, [])
        for pref in prefs:
            if pref in transforms:
                return pref

        return None


def generate_curated_topics(appspec: AppSpec) -> list[CuratedTopicConfig]:
    """Convenience function to generate all curated topics.

    Args:
        appspec: Application specification

    Returns:
        List of curated topic configurations
    """
    generator = CuratedTopicGenerator(appspec)
    return generator.generate()
