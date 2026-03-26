"""
Unified field value generator for tests, fixtures, and mock data.

Provides a single ``generate_field_value`` function that covers all field
types defined in :class:`~dazzle.core.ir.fields.FieldTypeKind`.  The six
previously independent implementations have been consolidated here.

Public API
----------
- ``generate_field_value(field, *, index, unique_suffix)``  — FieldSpec-based
- ``generate_field_value_from_str(name, field_type, *, unique, max_length)``  — string-type-based
  (used by test_runner which reads type names from JSON schema files)
"""

import re
import uuid as _uuid_module
from datetime import datetime
from typing import Any

from dazzle.core.ir.fields import FieldSpec, FieldTypeKind

# ---------------------------------------------------------------------------
# Sample-data pools (used when index-based realistic values are requested)
# ---------------------------------------------------------------------------

_NAMES = ["Alice Johnson", "Bob Smith", "Carol Williams", "David Brown", "Eve Davis"]
_TITLES = [
    "Fix login page CSS",
    "Add unit tests",
    "Deploy to staging",
    "Review PR #42",
    "Update documentation",
    "Refactor auth module",
    "Add search feature",
    "Fix memory leak",
]
_DESCRIPTIONS = [
    "This needs to be done before the next release.",
    "High priority item from the last sprint review.",
    "Follow up from customer feedback.",
    "",
    "Blocked by upstream dependency.",
]


# ---------------------------------------------------------------------------
# Primary public function
# ---------------------------------------------------------------------------


def generate_field_value(
    field: FieldSpec,
    *,
    index: int = 0,
    unique_suffix: str = "",
    realistic: bool = False,
) -> Any:
    """Generate a sample value for a field based on its type.

    Parameters
    ----------
    field:
        The field specification from the IR.
    index:
        Zero-based row index.  Used to cycle through sample-data pools when
        *realistic* is ``True``, and as a numeric suffix for version/serial
        fields.
    unique_suffix:
        An explicit suffix to append to string values to ensure uniqueness.
        When empty and ``field.is_unique`` is set, a random UUID-hex fragment
        is generated automatically.
    realistic:
        When ``True``, returns human-readable pool values (names, titles,
        descriptions) rather than generic ``"Test …"`` strings.  Used by
        mock_data / preview pages.

    Returns
    -------
    Any
        A Python value compatible with the field type.  Returns ``None`` for
        UUID and REF fields when they are expected to be auto-generated or
        resolved externally.
    """
    if not field.type:
        return f"sample_{index}"

    kind = field.type.kind

    # ------------------------------------------------------------------
    # Compute the unique suffix once
    # ------------------------------------------------------------------
    if not unique_suffix and field.is_unique:
        unique_suffix = f"_{_uuid_module.uuid4().hex[:8]}"

    name = field.name
    name_lower = name.lower()

    # ------------------------------------------------------------------
    # Enum
    # ------------------------------------------------------------------
    if kind == FieldTypeKind.ENUM:
        if field.type.enum_values:
            return field.type.enum_values[index % len(field.type.enum_values)]
        return "default"

    # ------------------------------------------------------------------
    # Email (both EMAIL kind and fields named "email")
    # ------------------------------------------------------------------
    if kind == FieldTypeKind.EMAIL or name_lower == "email" or "email" in name_lower:
        if realistic:
            return f"user{index}@example.com"
        return f"test{unique_suffix}@example.com"

    # ------------------------------------------------------------------
    # UUID — typically auto-generated; return a real UUID for mock data
    # ------------------------------------------------------------------
    if kind == FieldTypeKind.UUID:
        if realistic:
            return str(_uuid_module.uuid4())
        return None  # callers handle None

    # ------------------------------------------------------------------
    # REF — external resolution needed; return UUID for mock data
    # ------------------------------------------------------------------
    if kind == FieldTypeKind.REF:
        if realistic:
            return str(_uuid_module.uuid4())
        return None  # callers handle None

    # ------------------------------------------------------------------
    # Well-known field-name patterns
    # ------------------------------------------------------------------
    if name_lower == "version":
        return f"1.0.{index}"
    if name_lower in ("serial_number", "serialnumber"):
        return f"SN{index or 1}{unique_suffix}"

    # ------------------------------------------------------------------
    # Type-based generation
    # ------------------------------------------------------------------
    if kind == FieldTypeKind.STR:
        max_len = field.type.max_length or 50
        if realistic:
            if "name" in name_lower:
                return _NAMES[index % len(_NAMES)]
            if "title" in name_lower:
                return _TITLES[index % len(_TITLES)]
            return f"{name}_{index}"
        # Unique short fields: use hex only
        if field.is_unique and max_len <= 16:
            return _uuid_module.uuid4().hex[:max_len]
        value = f"Test {name}{unique_suffix}"
        if len(value) > max_len:
            if unique_suffix and max_len >= len(unique_suffix) + 1:
                value = value[: max_len - len(unique_suffix)] + unique_suffix
            else:
                value = value[:max_len]
        return value

    if kind == FieldTypeKind.TEXT:
        if realistic:
            return _DESCRIPTIONS[index % len(_DESCRIPTIONS)]
        return f"Test description for {name}{unique_suffix}"

    if kind == FieldTypeKind.INT:
        if realistic:
            import random

            return random.randint(1, 100)  # noqa: S311
        return 1

    if kind == FieldTypeKind.DECIMAL:
        if realistic:
            import random

            return round(random.uniform(10.0, 1000.0), 2)  # noqa: S311
        return 10.0

    if kind == FieldTypeKind.BOOL:
        if realistic:
            return index % 3 != 0
        return True

    if kind == FieldTypeKind.DATE:
        if realistic:
            import random
            from datetime import date, timedelta

            return (date.today() + timedelta(days=random.randint(-30, 30))).isoformat()  # noqa: S311
        return datetime.now().strftime("%Y-%m-%d")

    if kind == FieldTypeKind.DATETIME:
        if realistic:
            import random
            from datetime import timedelta

            return (datetime.now() + timedelta(hours=random.randint(-72, 72))).isoformat()  # noqa: S311
        return datetime.now().isoformat()

    if kind == FieldTypeKind.URL:
        return f"https://example.com/{name}{unique_suffix}"

    if kind == FieldTypeKind.FILE:
        return f"test_file{unique_suffix}.txt"

    if kind == FieldTypeKind.JSON:
        return {"key": f"value{unique_suffix}"}

    if kind == FieldTypeKind.MONEY:
        currency = field.type.currency_code or "USD"
        return {f"{name}_minor": 10000, f"{name}_currency": currency}

    if kind == FieldTypeKind.TIMEZONE:
        return "Europe/London"

    # Relationship kinds — not directly representable as a scalar value
    if kind in (
        FieldTypeKind.HAS_MANY,
        FieldTypeKind.HAS_ONE,
        FieldTypeKind.EMBEDS,
        FieldTypeKind.BELONGS_TO,
    ):
        return None

    # Fallback
    return f"test_{name}{unique_suffix}"


# ---------------------------------------------------------------------------
# String-type-based helper (for test_runner which uses JSON schema dicts)
# ---------------------------------------------------------------------------


def generate_field_value_from_str(
    name: str,
    field_type: str,
    *,
    unique: bool = False,
    max_length: int | None = None,
) -> Any:
    """Generate a test value given a field *name* and a *type string*.

    This function is used by :class:`~dazzle.testing.test_runner.DazzleClient`
    which reads field schemas from JSON design files rather than live
    :class:`~dazzle.core.ir.fields.FieldSpec` objects.

    Parameters
    ----------
    name:
        The field name (e.g. ``"email"``, ``"title"``).
    field_type:
        Lowercase type string as stored in designs.json
        (e.g. ``"str"``, ``"str(200)"``, ``"enum(draft,issued)"``, ``"ref"``).
    unique:
        Whether the field has a unique constraint.  When ``True`` a random
        UUID-hex fragment is appended to string values.
    max_length:
        Optional maximum length for string fields.  When ``None`` and
        *field_type* contains ``"str(N)"`` the value is parsed automatically.
    """
    field_type = field_type.lower()

    # Parse max_length from type string if not provided explicitly
    if max_length is None and "str" in field_type:
        ml_match = re.search(r"str\((\d+)\)", field_type)
        if ml_match:
            max_length = int(ml_match.group(1))

    # For short unique fields use hex only
    if max_length is not None and max_length <= 16 and unique:
        return _uuid_module.uuid4().hex[:max_length]

    unique_suffix = f"_{_uuid_module.uuid4().hex[:8]}" if unique else ""

    name_lower = name.lower()

    # Handle enum types
    enum_match = re.search(r"enum\(([^)]+)\)", field_type)
    if enum_match:
        values = enum_match.group(1).split(",")
        return values[0].strip()

    # Field-name patterns
    if name_lower == "email" or "email" in field_type:
        value = f"test{unique_suffix}@example.com"
        return value

    if name_lower in ("serial_number", "serialnumber", "serial"):
        return f"SN{unique_suffix or '_' + _uuid_module.uuid4().hex[:8]}"

    if name_lower == "version":
        return f"1.0.{_uuid_module.uuid4().hex[:6]}"

    # Type-based
    if "uuid" in field_type:
        return str(_uuid_module.uuid4())

    if "str" in field_type:
        value = f"Test {name}{unique_suffix}"
    elif "text" in field_type:
        value = f"Test description for {name}{unique_suffix}"
    elif "int" in field_type:
        return 1
    elif "decimal" in field_type or "float" in field_type:
        return 10.0
    elif "bool" in field_type:
        return True
    elif "datetime" in field_type:
        return datetime.now().isoformat()
    elif "date" in field_type:
        return datetime.now().strftime("%Y-%m-%d")
    elif "url" in field_type:
        return f"https://example.com/{name}{unique_suffix}"
    elif "file" in field_type:
        return f"test_file{unique_suffix}.txt"
    elif "json" in field_type:
        return {"key": f"value{unique_suffix}"}
    else:
        value = f"test_{name}{unique_suffix}"

    # Truncate to max_length if specified (preserving unique suffix)
    if max_length is not None and isinstance(value, str) and len(value) > max_length:
        if unique:
            suffix = unique_suffix
            prefix_budget = max_length - len(suffix)
            if prefix_budget > 0:
                value = value[:prefix_budget] + suffix
            else:
                value = _uuid_module.uuid4().hex[:max_length]
        else:
            value = value[:max_length]

    return value
