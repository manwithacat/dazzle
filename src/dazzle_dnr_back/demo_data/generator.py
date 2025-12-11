"""
Faker-based demo data generator for Dazzle Bar (v0.8.5).

Generates realistic demo data based on entity schemas.
"""

from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle_dnr_back.specs.entity import EntitySpec, FieldSpec, ScalarType

# Try to import Faker, but allow fallback to basic generation
try:
    from faker import Faker

    FAKER_AVAILABLE = True
except ImportError:
    FAKER_AVAILABLE = False
    Faker = None


class DemoDataGenerator:
    """
    Generates realistic demo data for entities.

    Uses Faker when available, otherwise falls back to basic generation.
    """

    def __init__(self, seed: int | None = None) -> None:
        """
        Initialize the generator.

        Args:
            seed: Random seed for reproducible data generation
        """
        self.seed = seed
        if seed is not None:
            random.seed(seed)

        if FAKER_AVAILABLE:
            self.faker = Faker()
            if seed is not None:
                Faker.seed(seed)
        else:
            self.faker = None

        # Counter for unique names
        self._name_counter = 0

    def generate_value(self, field: FieldSpec) -> Any:
        """
        Generate a value for a field based on its type.

        Args:
            field: Field specification

        Returns:
            Generated value
        """

        field_type = field.type

        # Handle enum fields
        if field_type.kind == "enum" and field_type.enum_values:
            return random.choice(field_type.enum_values)

        # Handle ref fields (return None, will be resolved by seeder)
        if field_type.kind == "ref":
            return None

        # Handle scalar fields
        scalar_type = field_type.scalar_type
        if scalar_type is None:
            return None

        # Generate based on field name hints first
        name_lower = field.name.lower()
        value = self._generate_by_field_name(name_lower, scalar_type, field_type.max_length)
        if value is not None:
            return value

        # Fall back to type-based generation
        return self._generate_by_type(scalar_type, field_type.max_length)

    def _generate_by_field_name(
        self, name: str, scalar_type: ScalarType, max_length: int | None
    ) -> Any:
        """
        Generate a value based on field name hints.

        Args:
            name: Field name (lowercase)
            scalar_type: Scalar type
            max_length: Maximum length for string types

        Returns:
            Generated value or None if no hint matched
        """

        if not self.faker:
            return None

        # Name hints
        if name in ("name", "full_name", "fullname"):
            return self.faker.name()
        if name in ("first_name", "firstname", "given_name"):
            return self.faker.first_name()
        if name in ("last_name", "lastname", "surname", "family_name"):
            return self.faker.last_name()
        if name in ("company", "company_name", "organization"):
            return self.faker.company()

        # Contact hints
        if name in ("email", "email_address"):
            return self.faker.email()
        if name in ("phone", "phone_number", "telephone"):
            return self.faker.phone_number()[:20]  # Limit length

        # Address hints
        if name in ("address", "street_address"):
            return self.faker.street_address()
        if name == "city":
            return self.faker.city()
        if name in ("state", "province"):
            return self.faker.state() if hasattr(self.faker, "state") else self.faker.city()
        if name in ("country", "country_name"):
            return self.faker.country()
        if name in ("zip", "zip_code", "postal_code", "postcode"):
            return self.faker.postcode()

        # Text hints
        if name in ("title", "subject", "heading"):
            return self.faker.sentence(nb_words=4).rstrip(".")
        if name in ("description", "summary", "notes", "content", "body"):
            return self.faker.paragraph()

        # Web hints
        if name in ("url", "website", "link", "homepage"):
            return self.faker.url()
        if name in ("username", "user_name"):
            return self.faker.user_name()

        # Amount hints
        if name in ("price", "cost", "amount", "total", "subtotal"):
            return Decimal(str(round(random.uniform(10, 1000), 2)))
        if name in ("quantity", "qty", "count"):
            return random.randint(1, 100)

        return None

    def _generate_by_type(self, scalar_type: ScalarType, max_length: int | None) -> Any:
        """
        Generate a value based on scalar type.

        Args:
            scalar_type: Scalar type
            max_length: Maximum length for string types

        Returns:
            Generated value
        """
        from dazzle_dnr_back.specs.entity import ScalarType

        if scalar_type == ScalarType.STR:
            if self.faker:
                text = self.faker.sentence(nb_words=3).rstrip(".")
            else:
                self._name_counter += 1
                text = f"Item {self._name_counter}"
            if max_length:
                text = text[:max_length]
            return text

        if scalar_type == ScalarType.TEXT:
            if self.faker:
                return self.faker.paragraph()
            return "Sample text content."

        if scalar_type == ScalarType.INT:
            return random.randint(1, 100)

        if scalar_type == ScalarType.DECIMAL:
            return Decimal(str(round(random.uniform(0, 1000), 2)))

        if scalar_type == ScalarType.BOOL:
            return random.choice([True, False])

        if scalar_type == ScalarType.DATE:
            days_offset = random.randint(-365, 365)
            return date.today() + timedelta(days=days_offset)

        if scalar_type == ScalarType.DATETIME:
            days_offset = random.randint(-365, 365)
            return datetime.now() + timedelta(days=days_offset)

        if scalar_type == ScalarType.UUID:
            return str(uuid.uuid4())

        if scalar_type == ScalarType.EMAIL:
            if self.faker:
                return self.faker.email()
            return f"user{random.randint(1, 1000)}@example.com"

        if scalar_type == ScalarType.URL:
            if self.faker:
                return self.faker.url()
            return f"https://example.com/{random.randint(1, 1000)}"

        if scalar_type == ScalarType.JSON:
            return {}

        # File types return None (need actual files)
        if scalar_type in (ScalarType.FILE, ScalarType.IMAGE):
            return None

        if scalar_type == ScalarType.RICHTEXT:
            if self.faker:
                return f"## {self.faker.sentence()}\n\n{self.faker.paragraph()}"
            return "## Sample\n\nSample rich text content."

        return None

    def generate_entity(
        self,
        entity: EntitySpec,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Generate a complete entity instance.

        Args:
            entity: Entity specification
            overrides: Values to override generated data

        Returns:
            Dictionary of field values
        """
        data: dict[str, Any] = {}

        for field in entity.fields:
            # Check if overridden
            if overrides and field.name in overrides:
                data[field.name] = overrides[field.name]
                continue

            # Use default if available and not required
            if field.default is not None and not field.required:
                data[field.name] = field.default
                continue

            # Generate value
            value = self.generate_value(field)

            # Only include if required or we got a value
            if value is not None or field.required:
                data[field.name] = value

        return data

    def generate_entities(
        self,
        entity: EntitySpec,
        count: int,
        base_overrides: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Generate multiple entity instances.

        Args:
            entity: Entity specification
            count: Number of entities to generate
            base_overrides: Values to override for all generated entities

        Returns:
            List of generated entity dictionaries
        """
        entities = []
        for _ in range(count):
            entity_data = self.generate_entity(entity, overrides=base_overrides)
            entities.append(entity_data)
        return entities
