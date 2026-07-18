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

from dazzle.core.ir.demo_blueprint import FieldStrategy

if TYPE_CHECKING:
    from dazzle.core.ir.demo_blueprint import (
        DemoDataBlueprint,
        EntityBlueprint,
        FieldPattern,
    )

# Try to import Faker, fall back to basic generation if not available.
# Keep Faker typed as `type[Any] | None` so the optional-dep guard
# (FAKER_AVAILABLE check) narrows correctly at every call site.
try:
    from faker import Faker as _RealFaker

    Faker: type[Any] | None = _RealFaker
    FAKER_AVAILABLE = True
except ImportError:
    Faker = None
    FAKER_AVAILABLE = False


_DATE_LIKE_TOKENS = ("date", "time", "_at", "deadline", "due", "expires", "starts", "ends")
_REF_LIKE_SUFFIXES = ("_id", "_by", "_to")
_REF_LIKE_NAMES = ("created_by", "updated_by", "assigned_to", "assignee", "owner", "author", "user")

# Common created/updated field name pairs (TR-58 seed-quality invariant).
_CREATED_UPDATED_PAIRS: tuple[tuple[str, str], ...] = (
    ("created_at", "updated_at"),
    ("created", "updated"),
    ("date_created", "date_updated"),
    ("created_on", "updated_on"),
)


def _role_enum_values(entity: EntityBlueprint) -> list[str]:
    """Extract allowed ``role`` enum values from entity field_patterns."""
    for pattern in getattr(entity, "field_patterns", None) or []:
        fname = str(getattr(pattern, "field_name", "") or "").lower()
        if fname != "role":
            continue
        params = getattr(pattern, "params", None) or {}
        vals = params.get("enum_values") or []
        return [str(v) for v in vals if v]
    return []


def _resolve_persona_role(entity: EntityBlueprint, persona: Any) -> str:
    """Map persona.default_role onto the entity's role enum when present.

    Legacy blueprints and auto-scaffolded personas used ``role_staff`` /
    ``role_<persona_id>`` while example apps declare business enums like
    ``customer|agent|manager``. Invalid roles explode as 422 toasts on
    user detail (admin User List click).
    """
    raw = str(getattr(persona, "default_role", "") or "").strip()
    allowed = _role_enum_values(entity)
    if not allowed:
        return raw or "user"

    if raw in allowed:
        return raw
    # Strip legacy role_ prefix: role_staff → staff, role_agent → agent
    stripped = raw.removeprefix("role_") if raw.startswith("role_") else raw
    if stripped in allowed:
        return stripped

    pname = str(getattr(persona, "persona_name", "") or "").strip().lower()
    if pname in allowed:
        return pname
    # Common aliases
    aliases = {
        "staff": "agent",
        "support": "agent",
        "admin": "manager",
        "user": allowed[0],
    }
    if stripped in aliases and aliases[stripped] in allowed:
        return aliases[stripped]
    if pname in aliases and aliases[pname] in allowed:
        return aliases[pname]

    return allowed[0]


def _enforce_created_before_updated(row: dict[str, Any]) -> None:
    """Mutate *row* so each known created/updated pair has created ≤ updated.

    Compares ISO date or datetime strings lexicographically on the date
    prefix (YYYY-MM-DD). If updated is earlier, set updated = created.
    """
    for created_key, updated_key in _CREATED_UPDATED_PAIRS:
        if created_key not in row or updated_key not in row:
            continue
        created_val = row[created_key]
        updated_val = row[updated_key]
        if created_val is None or updated_val is None:
            continue
        created_s = str(created_val)
        updated_s = str(updated_val)
        # Date prefix comparison is safe for both date and datetime ISO forms.
        if updated_s[:10] < created_s[:10]:
            row[updated_key] = created_val


def _looks_like_ref_field(field_name: str) -> bool:
    lower = field_name.lower()
    if lower in _REF_LIKE_NAMES:
        return True
    return any(lower.endswith(suf) for suf in _REF_LIKE_SUFFIXES)


def _looks_like_uuid(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 36:
        return False
    # 8-4-4-4-12 hex format
    parts = value.split("-")
    return len(parts) == 5 and all(
        all(c in "0123456789abcdefABCDEF" for c in part) for part in parts
    )


def _strategy_value_obviously_wrong(pattern: FieldPattern, value: Any) -> bool:
    """Return True iff the generated value is clearly wrong for the field.

    #821 heuristic: blueprint authoring drift regularly produces
    mismatches between a field's name/intent and the value a strategy
    emits (``date_relative`` on a ref field → ISO date string in a
    UUID column; ``free_text_lorem`` on a ref field → lorem in a UUID
    column). This helper catches the common cases so the row gets a
    NULL for the bad field instead of failing the whole POST on a
    type-cast error.

    Kept deliberately narrow — it is NOT a full IR-aware validator
    (that is a larger follow-up). Two cases handled:

    1. ``date_relative`` produces a YYYY-MM-DD string on a field whose
       name doesn't look date-like.
    2. Any strategy emits a non-UUID string on a field whose name
       looks like a ref (\"created_by\", \"assigned_to\", etc.).
    """
    field_name_lower = pattern.field_name.lower()

    if pattern.strategy == FieldStrategy.DATE_RELATIVE and not any(
        token in field_name_lower for token in _DATE_LIKE_TOKENS
    ):
        if isinstance(value, str) and len(value) == 10 and value.count("-") == 2:
            return True

    if _looks_like_ref_field(field_name_lower):
        if isinstance(value, str) and not _looks_like_uuid(value):
            return True

    return False


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
        self.fake: Any = None
        if FAKER_AVAILABLE and Faker is not None:
            self.fake = Faker("en_GB")
            Faker.seed(self.seed)

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
        # Per-entity shuffle bags for STATIC_LIST random_pick so unique fields
        # (e.g. Ticket.ticket_number) do not collide within a batch when the
        # value list is long enough (#1624 / TR-48). Reset each entity pass.
        self._static_list_bags: dict[str, list[Any]] = {}

        for row_index in range(entity.row_count_default):
            row = self._generate_row(entity, row_index)
            rows.append(row)

        return rows

    def _generate_row(self, entity: EntityBlueprint, row_index: int = 0) -> dict[str, Any]:
        """Generate a single row for an entity.

        #821: when a field's strategy produces a value that clearly
        doesn't match the field's intent (e.g. ``date_relative`` on a
        ref/uuid field), drop that key from the row so the seed
        endpoint writes NULL rather than choking on a type mismatch.
        Heuristic, not a full IR validator — it catches the common
        authoring drift where a blueprint was duplicated and strategy
        names weren't updated for the new field semantics.
        """
        row: dict[str, Any] = {}
        # `__row_index__` lets the SEQUENTIAL strategy see the row's position
        # within its entity. The dunder key cannot collide with a real field
        # name (DSL field names are plain identifiers).
        context: dict[str, Any] = {"__row_index__": row_index}

        for pattern in entity.field_patterns:
            value = self.generate_field_value(pattern, context)
            if _strategy_value_obviously_wrong(pattern, value):
                continue
            row[pattern.field_name] = value
            context[pattern.field_name] = value

        # TR-58: independent date_relative draws can put updated_at *before*
        # created_at. Enforce created ≤ updated for the common pair (and
        # generic *_at siblings when both exist as comparable date strings).
        _enforce_created_before_updated(row)
        return row

    def generate_field_value(self, pattern: FieldPattern, context: dict[str, Any]) -> Any:
        """Generate a value based on a field pattern strategy.

        Args:
            pattern: FieldPattern defining the generation strategy
            context: Context with previously generated field values

        Returns:
            Generated value
        """
        strategy = pattern.strategy
        params = pattern.params

        if strategy == FieldStrategy.UUID_GENERATE:
            return str(uuid.uuid4())

        elif strategy == FieldStrategy.STATIC_LIST:
            values = list(params.get("values", ["default"]))
            if not values:
                return "default"
            if not params.get("random_pick", True):
                return values[0]
            # Without-replacement within an entity batch (#1624). When the
            # bag is empty (more rows than values) reshuffle and continue —
            # dups are then unavoidable without suffixes. Standalone
            # generate_field_value (no bag) keeps classic random.choice.
            bags = getattr(self, "_static_list_bags", None)
            if bags is None:
                return random.choice(values)
            bag_key = pattern.field_name
            bag = bags.get(bag_key)
            if not bag:
                bag = values[:]
                random.shuffle(bag)
                bags[bag_key] = bag
            return bags[bag_key].pop()

        elif strategy == FieldStrategy.SEQUENTIAL:
            # Deterministic cycle through `values` by row index. Unlike
            # STATIC_LIST's random pick (which clusters — `seed: 42` can put
            # every row on one value), this guarantees an even spread: N rows
            # over K values yield ceil(N/K) or floor(N/K) of each, so a
            # blueprint can guarantee ">=1 row per tenant".
            values = params.get("values", ["default"])
            if not values:
                return "default"
            row_index = context.get("__row_index__", 0)
            return values[row_index % len(values)]

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
                # Dispatch on the field name so a single PERSON_NAME
                # strategy can serve `first_name` / `last_name` / `name`
                # columns correctly. Without this, blueprints that mark
                # both `first_name` and `last_name` as `person_name` (the
                # default) get full names in BOTH columns — confusing
                # row data ("Martin Smith" / "Albert Clark" for the
                # same contact, with the email matching only the first).
                fname = pattern.field_name.lower()
                if fname in ("first_name", "firstname", "given_name"):
                    return self.fake.first_name()
                if fname in ("last_name", "lastname", "surname", "family_name"):
                    return self.fake.last_name()
                return self.fake.name()
            return f"Person {random.randint(1, 1000)}"

        elif strategy == FieldStrategy.COMPANY_NAME:
            if self.fake:
                return self.fake.company()
            return f"Company {random.randint(1, 1000)}"

        elif strategy == FieldStrategy.EMAIL_FROM_NAME:
            source_field = params.get("source_field", "full_name")
            domains = params.get("domains", ["example.test"])
            # Robust fallback chain: requested source_field → common name
            # fields → first+last concatenation → random suffix. Without
            # this, a missing `source_field` silently resolved to the
            # default `"user"` and every row produced the same email,
            # colliding on the unique-email constraint every entity
            # with email has. (Discovered in today's tool-sweep:
            # blueprint.json files across 4 apps had `source_field:
            # 'full_name'` but no entity had a `full_name` field.)
            name = context.get(source_field) or context.get("name") or context.get("full_name")
            if not name:
                first = context.get("first_name", "")
                last = context.get("last_name", "")
                name = f"{first} {last}".strip()
            if not name:
                name = f"user{random.randint(1000, 9999)}"
            # Convert name to email format
            email_name = str(name).lower().replace(" ", ".").replace("'", "")
            # Append a short suffix to guarantee uniqueness even when
            # two rows share a name (person_name draws from a finite
            # faker pool — collisions at row_count_default=20 are
            # common).
            suffix = random.randint(1000, 9999)
            domain = random.choice(domains)
            return f"{email_name}.{suffix}@{domain}"

        elif strategy == FieldStrategy.USERNAME_FROM_NAME:
            source_field = params.get("source_field", "full_name")
            # Same fallback chain as EMAIL_FROM_NAME — a missing
            # source_field silently collapsed to "user" and produced
            # duplicates across the batch.
            name = context.get(source_field) or context.get("name") or context.get("full_name")
            if not name:
                first = context.get("first_name", "")
                last = context.get("last_name", "")
                name = f"{first} {last}".strip()
            if not name:
                name = f"user{random.randint(1000, 9999)}"
            username = str(name).lower().replace(" ", "_").replace("'", "")
            # Uniqueness suffix (same rationale as EMAIL_FROM_NAME).
            suffix = random.randint(1000, 9999)
            return f"{username}_{suffix}"

        elif strategy == FieldStrategy.HASHED_PASSWORD_PLACEHOLDER:
            # Return a placeholder that indicates this needs hashing
            plaintext = params.get("plaintext_demo_password", "Demo1234!")
            return f"PLAINTEXT:{plaintext}"

        elif strategy == FieldStrategy.FREE_TEXT_LOREM:
            # TR-58: job_title / occupation fields must not emit lorem ipsum —
            # faker.job() (or a short static list) reads as real demo data.
            fname = pattern.field_name.lower()
            if any(
                tok in fname
                for tok in ("job_title", "jobtitle", "occupation", "role_title", "position_title")
            ) or fname in ("job", "occupation", "position", "role"):
                if self.fake and hasattr(self.fake, "job"):
                    return self.fake.job()
                return random.choice(
                    (
                        "Account Manager",
                        "Software Engineer",
                        "Operations Lead",
                        "Customer Success",
                        "Finance Analyst",
                    )
                )

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

            # Optional floor from a sibling field (e.g. updated_at not_before
            # created_at). ISO date/datetime prefixes compare correctly.
            not_before_field = params.get("not_before_field") or params.get("after_field")
            floor: date | None = None
            if not_before_field and context.get(not_before_field):
                raw = str(context[not_before_field])[:10]
                try:
                    floor = date.fromisoformat(raw)
                except ValueError:
                    floor = None

            offset_days = random.randint(min_offset, max_offset)
            result_date = base_date + timedelta(days=offset_days)
            if floor is not None and result_date < floor:
                # Sample on/after the floor, still within the original window
                # upper bound when possible; else clamp to floor.
                upper = base_date + timedelta(days=max_offset)
                if floor > upper:
                    result_date = floor
                else:
                    span = (upper - floor).days
                    result_date = floor + timedelta(days=random.randint(0, max(span, 0)))
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
                # `within_tenant`: keep the FK reference tenant-consistent —
                # restrict the pick to target rows in the same tenant as the
                # row being generated. Without it, `random.choice` over the
                # whole pool clusters children under one tenant (#1182) and
                # can even pair a child with a parent in a *different* tenant.
                # Falls back to the full pool when the current row has no
                # tenant_id or no target row shares it, so single-tenant
                # blueprints are unaffected.
                if params.get("within_tenant") and target_rows:
                    current_tenant = context.get("tenant_id")
                    if current_tenant is not None:
                        scoped = [r for r in target_rows if r.get("tenant_id") == current_tenant]
                        if scoped:
                            target_rows = scoped
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

    def _generate_users_from_blueprint(self, entity: EntityBlueprint) -> list[dict[str, Any]]:
        """Generate user records from persona blueprints."""
        rows: list[dict[str, Any]] = []
        self._generated_users = []

        # Get tenant IDs
        tenant_ids = [t["id"] for t in self._generated_data.get("Tenant", [])] or [
            str(uuid.uuid4())
        ]

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

                    # Emit both ``name`` and ``full_name`` so entities
                    # that declare either will find their column (#821).
                    # The seed endpoint filters by known_fields so the
                    # unused alias drops out harmlessly.
                    row: dict[str, Any] = {
                        "id": str(uuid.uuid4()),
                        "name": full_name,
                        "full_name": full_name,
                        "email": email,
                        "username": email_base.replace(".", "_"),
                        "password_hash": "PLAINTEXT:Demo1234!",
                        "persona": persona.persona_name,
                        # Clamp to User.role (or similar) enum when blueprint
                        # personas still carry legacy role_* defaults (#1625
                        # field: detail toast on admin User List).
                        "role": _resolve_persona_role(entity, persona),
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
