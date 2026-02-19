"""
Data generators for vendor mock responses.

Generates realistic fake data matching API pack foreign model field types.
Supports deterministic mode (seeded) for reproducible test data.
"""

from __future__ import annotations

import random
import re
import string
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any


class DataGenerator:
    """Generate realistic fake data for API pack foreign model fields.

    Args:
        seed: Optional seed for deterministic output. When set, identical
              calls produce identical data across runs.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._counters: dict[str, int] = {}

    def _next_counter(self, key: str) -> int:
        """Get the next sequential counter value for a key."""
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]

    def generate_field(self, field_name: str, field_spec: dict[str, Any]) -> Any:
        """Generate a value for a single field based on its type spec.

        Args:
            field_name: The field name (used for contextual generation).
            field_spec: Dict with at least 'type' key (e.g. 'str(50)', 'email').

        Returns:
            A realistic fake value matching the type.
        """
        type_str = field_spec.get("type", "str")
        required = field_spec.get("required", False)
        pk = field_spec.get("pk", False)

        # PK fields get sequential IDs
        if pk:
            return self._generate_pk(field_name, type_str)

        # Optional fields: 70% chance of having a value
        if not required and self._rng.random() < 0.3:
            return None

        return self._generate_value(field_name, type_str)

    def _generate_pk(self, field_name: str, type_str: str) -> Any:
        """Generate a primary key value."""
        if type_str == "uuid" or "uuid" in type_str:
            return str(uuid.UUID(int=self._rng.getrandbits(128), version=4))
        if type_str == "int":
            return self._next_counter(f"pk:{field_name}")
        # str-based PK — generate prefixed ID
        prefix = field_name[:3] if len(field_name) >= 3 else field_name
        counter = self._next_counter(f"pk:{field_name}")
        return f"{prefix}_{counter:06d}"

    def _generate_value(self, field_name: str, type_str: str) -> Any:
        """Generate a value based on field type string."""
        # Parse type string
        type_str = type_str.strip()

        # UUID
        if type_str == "uuid":
            return str(uuid.UUID(int=self._rng.getrandbits(128), version=4))

        # Integer
        if type_str == "int":
            return self._rng.randint(1, 10000)

        # Boolean
        if type_str == "bool":
            return self._rng.choice([True, False])

        # Email
        if type_str == "email":
            return self._generate_email(field_name)

        # Date
        if type_str == "date":
            return self._generate_date().isoformat()

        # Datetime
        if type_str == "datetime":
            return self._generate_datetime().isoformat()

        # Decimal
        m = re.match(r"decimal\((\d+),(\d+)\)", type_str)
        if m:
            precision, scale = int(m.group(1)), int(m.group(2))
            return self._generate_decimal(precision, scale)

        # Money
        if type_str == "money":
            return self._generate_decimal(13, 2)

        # Enum
        m = re.match(r"enum\[(.+)]", type_str)
        if m:
            values = [v.strip() for v in m.group(1).split(",")]
            return self._rng.choice(values)

        # JSON
        if type_str == "json":
            return self._generate_json(field_name)

        # String with max length
        m = re.match(r"str\((\d+)\)", type_str)
        if m:
            max_len = int(m.group(1))
            return self._generate_string(field_name, max_len)

        # Bare string or unknown — treat as str(100)
        if type_str in ("str", "text"):
            return self._generate_string(field_name, 100)

        # URL
        if type_str == "url":
            return f"https://example.com/{field_name}/{self._rng.randint(1, 9999)}"

        # Fallback
        return self._generate_string(field_name, 50)

    def _generate_email(self, field_name: str) -> str:
        """Generate a realistic email address."""
        first_names = ["james", "sarah", "alex", "emma", "oliver", "sophia", "liam", "mia"]
        last_names = ["smith", "jones", "taylor", "brown", "wilson", "davies", "evans"]
        domains = ["example.com", "test.co.uk", "demo.org", "mock.dev"]
        first = self._rng.choice(first_names)
        last = self._rng.choice(last_names)
        domain = self._rng.choice(domains)
        return f"{first}.{last}@{domain}"

    def _generate_date(self) -> date:
        """Generate a realistic date (within last 2 years)."""
        days_ago = self._rng.randint(1, 730)
        return date.today() - timedelta(days=days_ago)

    def _generate_datetime(self) -> datetime:
        """Generate a realistic datetime (within last 2 years)."""
        seconds_ago = self._rng.randint(60, 730 * 86400)
        return datetime.now(UTC) - timedelta(seconds=seconds_ago)

    def _generate_decimal(self, precision: int, scale: int) -> str:
        """Generate a decimal string with given precision and scale."""
        int_digits = precision - scale
        max_int = 10**int_digits - 1
        int_part = self._rng.randint(0, min(max_int, 99999))
        frac_part = self._rng.randint(0, 10**scale - 1)
        return f"{int_part}.{frac_part:0{scale}d}"

    def _generate_string(self, field_name: str, max_len: int) -> str:
        """Generate a contextual string based on field name."""
        # Common field name patterns
        name_lower = field_name.lower()

        if "name" in name_lower or "title" in name_lower:
            return self._generate_name(name_lower, max_len)
        if "phone" in name_lower:
            return self._generate_phone()
        if "country" in name_lower:
            return self._rng.choice(["GBR", "USA", "DEU", "FRA", "AUS"])[:max_len]
        if "status" in name_lower:
            return self._rng.choice(["active", "pending", "completed"])[:max_len]
        if "description" in name_lower or "comment" in name_lower:
            return self._generate_sentence(max_len)
        if "slug" in name_lower:
            return self._generate_slug(max_len)
        if "ip" in name_lower:
            return f"{self._rng.randint(1, 254)}.{self._rng.randint(0, 255)}.{self._rng.randint(0, 255)}.{self._rng.randint(1, 254)}"
        if "ua" in name_lower or "user_agent" in name_lower:
            return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"[:max_len]
        if "url" in name_lower or "src" in name_lower:
            return f"https://example.com/{field_name}/{self._rng.randint(1, 9999)}"[:max_len]

        # Generic string
        length = min(self._rng.randint(5, 30), max_len)
        return "".join(self._rng.choices(string.ascii_lowercase + " ", k=length)).strip()[:max_len]

    def _generate_name(self, field_hint: str, max_len: int) -> str:
        """Generate a name based on context."""
        first_names = ["James", "Sarah", "Oliver", "Emma", "Alexander", "Sophie"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Taylor"]

        if "first" in field_hint:
            return self._rng.choice(first_names)[:max_len]
        if "last" in field_hint:
            return self._rng.choice(last_names)[:max_len]
        if "company" in field_hint or "legal" in field_hint:
            companies = ["Acme Corp", "GlobalTech Ltd", "Sterling & Partners", "NovaSoft Inc"]
            return self._rng.choice(companies)[:max_len]

        first = self._rng.choice(first_names)
        last = self._rng.choice(last_names)
        return f"{first} {last}"[:max_len]

    def _generate_phone(self) -> str:
        """Generate a UK-format phone number."""
        return f"+44{self._rng.randint(7000000000, 7999999999)}"

    def _generate_sentence(self, max_len: int) -> str:
        """Generate a short sentence."""
        words = [
            "test",
            "mock",
            "data",
            "sample",
            "generated",
            "value",
            "item",
            "record",
            "entry",
            "example",
            "verification",
            "check",
            "review",
        ]
        count = self._rng.randint(3, 8)
        sentence = " ".join(self._rng.choices(words, k=count)).capitalize()
        return sentence[:max_len]

    def _generate_slug(self, max_len: int) -> str:
        """Generate a URL-friendly slug."""
        words = ["test", "mock", "sample", "demo", "example"]
        slug = "-".join(self._rng.choices(words, k=self._rng.randint(2, 3)))
        return slug[:max_len]

    def _generate_json(self, field_name: str) -> Any:
        """Generate contextual JSON data."""
        name_lower = field_name.lower()
        if "tags" in name_lower or "labels" in name_lower:
            return [self._rng.choice(["verified", "pending", "review", "flagged"])]
        if "match" in name_lower or "source" in name_lower:
            return []
        if "field" in name_lower or "schema" in name_lower:
            return []
        if "address" in name_lower:
            return {
                "street": f"{self._rng.randint(1, 200)} Test Street",
                "city": self._rng.choice(["London", "Manchester", "Birmingham"]),
                "postcode": f"SW{self._rng.randint(1, 20)} {self._rng.randint(1, 9)}AB",
                "country": "GBR",
            }
        return {}

    def generate_model(self, model_name: str, fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Generate a complete model instance from foreign model field definitions.

        Args:
            model_name: The model name (for ID prefixing).
            fields: Dict mapping field_name -> field_spec.

        Returns:
            Dict with all fields populated.
        """
        result: dict[str, Any] = {}
        for field_name, field_spec in fields.items():
            result[field_name] = self.generate_field(field_name, field_spec)
        return result
