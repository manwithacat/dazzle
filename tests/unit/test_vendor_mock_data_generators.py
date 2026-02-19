"""Tests for vendor mock data generators."""

from __future__ import annotations

import re
from datetime import date, datetime

from dazzle.testing.vendor_mock.data_generators import DataGenerator


class TestFieldGeneration:
    """Test individual field type generation."""

    def test_uuid_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("id", {"type": "uuid", "pk": True})
        assert isinstance(val, str)
        # UUID4 format
        assert re.match(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", val)

    def test_int_pk(self) -> None:
        gen = DataGenerator(seed=42)
        val1 = gen.generate_field("id", {"type": "int", "pk": True})
        val2 = gen.generate_field("id", {"type": "int", "pk": True})
        assert val1 == 1
        assert val2 == 2

    def test_str_pk_prefixed(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("applicant_id", {"type": "str(50)", "pk": True})
        assert val.startswith("app_")
        assert len(val) <= 50

    def test_email_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("email", {"type": "email", "required": True})
        assert "@" in val
        assert "." in val

    def test_date_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("created", {"type": "date", "required": True})
        # Should be ISO format string
        parsed = date.fromisoformat(val)
        assert parsed <= date.today()

    def test_datetime_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("created_at", {"type": "datetime", "required": True})
        # Should parse as ISO datetime
        parsed = datetime.fromisoformat(val)
        assert parsed is not None

    def test_decimal_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("amount", {"type": "decimal(13,2)", "required": True})
        assert isinstance(val, str)
        parts = val.split(".")
        assert len(parts) == 2
        assert len(parts[1]) == 2  # 2 decimal places

    def test_money_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("total", {"type": "money", "required": True})
        assert isinstance(val, str)
        assert "." in val

    def test_enum_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field(
            "status", {"type": "enum[active,pending,completed]", "required": True}
        )
        assert val in ["active", "pending", "completed"]

    def test_bool_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("verified", {"type": "bool", "required": True})
        assert isinstance(val, bool)

    def test_int_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("count", {"type": "int", "required": True})
        assert isinstance(val, int)
        assert val >= 1

    def test_json_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("metadata", {"type": "json", "required": True})
        assert isinstance(val, (dict, list))

    def test_json_tags_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("tags", {"type": "json", "required": True})
        assert isinstance(val, list)

    def test_json_address_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("address", {"type": "json", "required": True})
        assert isinstance(val, dict)
        assert "street" in val

    def test_str_with_max_length(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("name", {"type": "str(50)", "required": True})
        assert isinstance(val, str)
        assert len(val) <= 50

    def test_bare_str_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("notes", {"type": "str", "required": True})
        assert isinstance(val, str)

    def test_url_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("website", {"type": "url", "required": True})
        assert val.startswith("https://")


class TestContextualGeneration:
    """Test that field names influence generated content."""

    def test_name_field_looks_like_name(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("first_name", {"type": "str(100)", "required": True})
        # Should be a first name, not random chars
        assert val[0].isupper()

    def test_phone_field_format(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("phone", {"type": "str(20)", "required": True})
        assert val.startswith("+44")

    def test_country_field(self) -> None:
        gen = DataGenerator(seed=42)
        val = gen.generate_field("country", {"type": "str(3)", "required": True})
        assert len(val) == 3
        assert val.isupper()


class TestDeterminism:
    """Test deterministic (seeded) generation."""

    def test_same_seed_same_output(self) -> None:
        gen1 = DataGenerator(seed=123)
        gen2 = DataGenerator(seed=123)

        for fname in ["email", "name", "amount", "status"]:
            spec = {"type": "str(100)", "required": True}
            if fname == "email":
                spec["type"] = "email"
            elif fname == "amount":
                spec["type"] = "decimal(13,2)"
            elif fname == "status":
                spec["type"] = "enum[a,b,c]"

            val1 = gen1.generate_field(fname, spec)
            val2 = gen2.generate_field(fname, spec)
            assert val1 == val2, f"Mismatch for {fname}: {val1} != {val2}"

    def test_different_seed_different_output(self) -> None:
        gen1 = DataGenerator(seed=1)
        gen2 = DataGenerator(seed=999)
        # Generate enough fields that statistical collision is near-impossible
        vals1 = [
            gen1.generate_field("x", {"type": "str(100)", "required": True}) for _ in range(10)
        ]
        vals2 = [
            gen2.generate_field("x", {"type": "str(100)", "required": True}) for _ in range(10)
        ]
        assert vals1 != vals2


class TestModelGeneration:
    """Test complete model generation."""

    def test_generate_model(self) -> None:
        gen = DataGenerator(seed=42)
        fields = {
            "id": {"type": "str(50)", "required": True, "pk": True},
            "email": {"type": "email"},
            "first_name": {"type": "str(100)"},
            "status": {"type": "enum[active,pending]", "required": True},
        }
        result = gen.generate_model("Applicant", fields)
        assert "id" in result
        assert result["id"].startswith("id_")
        assert result["status"] in ("active", "pending")

    def test_optional_fields_sometimes_none(self) -> None:
        gen = DataGenerator(seed=42)
        fields = {
            "id": {"type": "int", "required": True, "pk": True},
            "optional_field": {"type": "str(50)"},
        }
        # Generate many — some optional fields should be None
        results = [gen.generate_model("Test", fields) for _ in range(30)]
        none_count = sum(1 for r in results if r["optional_field"] is None)
        assert none_count > 0, "Expected some optional fields to be None"
        assert none_count < 30, "Expected some optional fields to have values"
