"""
Demo Data Blueprint Generator.

Generates demo data files (CSV/JSONL) from DemoDataBlueprint definitions.
"""

from __future__ import annotations

import csv
import json
import random
import string
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.core.ir.demo_blueprint import (
        DemoDataBlueprint,
        EntityBlueprint,
        FieldPattern,
    )

# Try to import Faker, fall back to basic generation if not available
try:
    from faker import Faker

    FAKER_AVAILABLE = True
except ImportError:
    FAKER_AVAILABLE = False
    Faker = None


class BlueprintDataGenerator:
    """Generate demo data from a DemoDataBlueprint.

    This generator creates CSV or JSONL files with realistic,
    domain-flavored demo data based on the blueprint configuration.
    """

    def __init__(self, blueprint: DemoDataBlueprint, seed: int | None = None):
        """Initialize the generator.

        Args:
            blueprint: DemoDataBlueprint to generate from
            seed: Optional random seed for reproducibility
        """
        self.blueprint = blueprint
        self.seed = seed or blueprint.seed or 42

        # Initialize random state
        random.seed(self.seed)

        # Initialize Faker if available
        if FAKER_AVAILABLE:
            self.fake = Faker("en_GB")
            Faker.seed(self.seed)
        else:
            self.fake = None

        # Track generated data for foreign key references
        self._generated_data: dict[str, list[dict[str, Any]]] = {}

        # Track row counts
        self.row_counts: dict[str, int] = {}

        # Track generated users for login matrix
        self._generated_users: list[dict[str, Any]] = []

    def generate_all(
        self,
        output_dir: Path,
        format: str = "csv",
        entities: list[str] | None = None,
    ) -> dict[str, Path]:
        """Generate demo data files for all entities.

        Args:
            output_dir: Directory to write files to
            format: Output format ("csv" or "jsonl")
            entities: Optional list of entity names to generate

        Returns:
            Dictionary mapping entity names to file paths
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        files: dict[str, Path] = {}

        # Generate tenants first (if entity exists)
        tenant_blueprints = [e for e in self.blueprint.entities if e.name.lower() == "tenant"]
        for entity in tenant_blueprints:
            if entities and entity.name not in entities:
                continue
            data = self._generate_tenants_from_blueprint()
            self._generated_data[entity.name] = data
            self.row_counts[entity.name] = len(data)
            file_path = self._write_data(output_dir, entity.name, data, format)
            files[entity.name] = file_path

        # Generate users second (if entity exists)
        user_blueprints = [e for e in self.blueprint.entities if e.name.lower() == "user"]
        for entity in user_blueprints:
            if entities and entity.name not in entities:
                continue
            data = self._generate_users_from_blueprint(entity)
            self._generated_data[entity.name] = data
            self.row_counts[entity.name] = len(data)
            file_path = self._write_data(output_dir, entity.name, data, format)
            files[entity.name] = file_path

        # Generate other entities
        for entity in self.blueprint.entities:
            if entity.name.lower() in ("tenant", "user"):
                continue
            if entities and entity.name not in entities:
                continue

            data = self.generate_entity(entity)
            self._generated_data[entity.name] = data
            self.row_counts[entity.name] = len(data)
            file_path = self._write_data(output_dir, entity.name, data, format)
            files[entity.name] = file_path

        return files

    def generate_entity(self, entity: EntityBlueprint) -> list[dict[str, Any]]:
        """Generate rows for a single entity.

        Args:
            entity: EntityBlueprint defining the entity

        Returns:
            List of row dictionaries
        """
        rows: list[dict[str, Any]] = []

        for _ in range(entity.row_count_default):
            row = self._generate_row(entity)
            rows.append(row)

        return rows

    def _generate_row(self, entity: EntityBlueprint) -> dict[str, Any]:
        """Generate a single row for an entity."""
        row: dict[str, Any] = {}
        context: dict[str, Any] = {}

        for pattern in entity.field_patterns:
            value = self.generate_field_value(pattern, context)
            row[pattern.field_name] = value
            context[pattern.field_name] = value

        return row

    def generate_field_value(
        self, pattern: FieldPattern, context: dict[str, Any]
    ) -> Any:
        """Generate a value based on a field pattern strategy.

        Args:
            pattern: FieldPattern defining the generation strategy
            context: Context with previously generated field values

        Returns:
            Generated value
        """
        from dazzle.core.ir.demo_blueprint import FieldStrategy

        strategy = pattern.strategy
        params = pattern.params

        if strategy == FieldStrategy.UUID_GENERATE:
            return str(uuid.uuid4())

        elif strategy == FieldStrategy.STATIC_LIST:
            values = params.get("values", ["default"])
            if params.get("random_pick", True):
                return random.choice(values)
            return values[0] if values else "default"

        elif strategy == FieldStrategy.ENUM_WEIGHTED:
            enum_values = params.get("enum_values", [])
            weights = params.get("weights", [])
            if enum_values:
                if weights and len(weights) == len(enum_values):
                    return random.choices(enum_values, weights=weights)[0]
                return random.choice(enum_values)
            return None

        elif strategy == FieldStrategy.PERSON_NAME:
            if self.fake:
                return self.fake.name()
            return f"Person {random.randint(1, 1000)}"

        elif strategy == FieldStrategy.COMPANY_NAME:
            if self.fake:
                return self.fake.company()
            return f"Company {random.randint(1, 1000)}"

        elif strategy == FieldStrategy.EMAIL_FROM_NAME:
            source_field = params.get("source_field", "full_name")
            domains = params.get("domains", ["example.test"])
            name = context.get(source_field, "user")
            # Convert name to email format
            email_name = name.lower().replace(" ", ".").replace("'", "")
            domain = random.choice(domains)
            return f"{email_name}@{domain}"

        elif strategy == FieldStrategy.USERNAME_FROM_NAME:
            source_field = params.get("source_field", "full_name")
            name = context.get(source_field, "user")
            username = name.lower().replace(" ", "_").replace("'", "")
            return username

        elif strategy == FieldStrategy.HASHED_PASSWORD_PLACEHOLDER:
            # Return a placeholder that indicates this needs hashing
            plaintext = params.get("plaintext_demo_password", "Demo1234!")
            return f"PLAINTEXT:{plaintext}"

        elif strategy == FieldStrategy.FREE_TEXT_LOREM:
            min_words = params.get("min_words", 3)
            max_words = params.get("max_words", 10)
            word_count = random.randint(min_words, max_words)

            if self.fake:
                return self.fake.sentence(nb_words=word_count)
            return " ".join(
                "".join(random.choices(string.ascii_lowercase, k=random.randint(3, 8)))
                for _ in range(word_count)
            )

        elif strategy == FieldStrategy.NUMERIC_RANGE:
            min_val = params.get("min", 0)
            max_val = params.get("max", 100)
            decimals = params.get("decimals", 0)
            if decimals > 0:
                value = random.uniform(min_val, max_val)
                return round(value, decimals)
            return random.randint(int(min_val), int(max_val))

        elif strategy == FieldStrategy.CURRENCY_AMOUNT:
            min_val = params.get("min", 0)
            max_val = params.get("max", 10000)
            decimals = params.get("decimals", 2)
            bias = params.get("bias", "uniform")

            if bias == "lognormal":
                # Lognormal distribution for more realistic amounts
                mean = (min_val + max_val) / 2
                value = random.lognormvariate(0, 1) * mean / 2
                value = max(min_val, min(max_val, value))
            else:
                value = random.uniform(min_val, max_val)

            return round(value, decimals)

        elif strategy == FieldStrategy.DATE_RELATIVE:
            anchor = params.get("anchor", "today")
            min_offset = params.get("min_offset_days", -30)
            max_offset = params.get("max_offset_days", 0)

            if anchor == "today":
                base_date = date.today()
            else:
                base_date = date.today()

            offset_days = random.randint(min_offset, max_offset)
            result_date = base_date + timedelta(days=offset_days)
            return result_date.isoformat()

        elif strategy == FieldStrategy.BOOLEAN_WEIGHTED:
            true_weight = params.get("true_weight", 0.5)
            return random.random() < true_weight

        elif strategy == FieldStrategy.FOREIGN_KEY:
            target_entity = params.get("target_entity", "")
            target_field = params.get("target_field", "id")

            # Look up from generated data
            if target_entity in self._generated_data:
                target_rows = self._generated_data[target_entity]
                if target_rows:
                    target_row = random.choice(target_rows)
                    return target_row.get(target_field)

            # If no data yet, generate a UUID placeholder
            return str(uuid.uuid4())

        elif strategy == FieldStrategy.COMPOSITE:
            # Composite combines multiple fields
            template = params.get("template", "{field1}-{field2}")
            return template.format(**context)

        elif strategy == FieldStrategy.CUSTOM_PROMPT:
            # For custom prompts, return a placeholder
            prompt = params.get("prompt", "custom value")
            return f"[{prompt}]"

        # Default fallback
        return None

    def _generate_tenants_from_blueprint(self) -> list[dict[str, Any]]:
        """Generate tenant records from tenant blueprints."""
        rows: list[dict[str, Any]] = []

        for tenant in self.blueprint.tenants:
            row = {
                "id": str(uuid.uuid4()),
                "name": tenant.name,
                "slug": tenant.slug or tenant.name.lower().replace(" ", "-"),
            }
            rows.append(row)

        return rows

    def _generate_users_from_blueprint(
        self, entity: EntityBlueprint
    ) -> list[dict[str, Any]]:
        """Generate user records from persona blueprints."""
        rows: list[dict[str, Any]] = []
        self._generated_users = []

        # Get tenant IDs
        tenant_ids = [
            t["id"] for t in self._generated_data.get("Tenant", [])
        ] or [str(uuid.uuid4())]

        # Track used names to avoid duplicates
        used_emails: set[str] = set()

        for tenant_id in tenant_ids:
            tenant_data = next(
                (t for t in self._generated_data.get("Tenant", []) if t["id"] == tenant_id),
                {"slug": "demo"},
            )
            domain = f"{tenant_data.get('slug', 'demo')}.test"

            for persona in self.blueprint.personas:
                for i in range(persona.default_user_count):
                    # Generate name
                    if self.fake:
                        full_name = self.fake.name()
                    else:
                        full_name = f"{persona.persona_name} User {i + 1}"

                    # Generate unique email
                    email_base = full_name.lower().replace(" ", ".").replace("'", "")
                    email = f"{email_base}@{domain}"
                    counter = 1
                    while email in used_emails:
                        email = f"{email_base}{counter}@{domain}"
                        counter += 1
                    used_emails.add(email)

                    row: dict[str, Any] = {
                        "id": str(uuid.uuid4()),
                        "full_name": full_name,
                        "email": email,
                        "username": email_base.replace(".", "_"),
                        "password_hash": "PLAINTEXT:Demo1234!",
                        "persona": persona.persona_name,
                        "role": persona.default_role,
                    }

                    # Add tenant_id if entity is tenant-scoped
                    if entity.tenant_scoped:
                        row["tenant_id"] = tenant_id

                    rows.append(row)

                    # Track for login matrix
                    self._generated_users.append(
                        {
                            "tenant": next(
                                (
                                    t["name"]
                                    for t in self._generated_data.get("Tenant", [])
                                    if t["id"] == tenant_id
                                ),
                                "Default",
                            ),
                            "persona": persona.persona_name,
                            "email": email,
                            "password": "Demo1234!",
                        }
                    )

        return rows

    def _write_data(
        self,
        output_dir: Path,
        entity_name: str,
        data: list[dict[str, Any]],
        format: str,
    ) -> Path:
        """Write data to a file.

        Args:
            output_dir: Directory to write to
            entity_name: Entity name (used for filename)
            data: List of row dictionaries
            format: Output format ("csv" or "jsonl")

        Returns:
            Path to the written file
        """
        if format == "jsonl":
            file_path = output_dir / f"{entity_name}.jsonl"
            with open(file_path, "w", encoding="utf-8") as f:
                for row in data:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            file_path = output_dir / f"{entity_name}.csv"
            if data:
                fieldnames = list(data[0].keys())
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(data)
            else:
                # Empty file with no content
                file_path.write_text("", encoding="utf-8")

        return file_path

    def get_login_matrix(self) -> str:
        """Generate a markdown login matrix for demo users.

        Returns:
            Markdown table of demo login credentials
        """
        lines = [
            "# Demo Login Matrix",
            "",
            "| Tenant | Persona | Email | Password |",
            "|--------|---------|-------|----------|",
        ]

        for user in self._generated_users:
            lines.append(
                f"| {user['tenant']} | {user['persona']} | {user['email']} | {user['password']} |"
            )

        if not self._generated_users:
            lines.append("| (no users generated) | - | - | - |")

        return "\n".join(lines)
