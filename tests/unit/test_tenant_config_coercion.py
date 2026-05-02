"""Tests for #957 cycle 7 — `dazzle.tenant.config_coercion`.

Coerces raw JSONB config dicts against a `TenancySpec.per_tenant_config`
schema. The coercion runs once per request (cycle 8) so callers can
rely on consistent types via ``request.state.tenant_config`` without
defensive isinstance/cast.
"""

from __future__ import annotations

from dataclasses import asdict, fields

from dazzle.tenant.config_coercion import coerce_config
from dazzle.tenant.registry import TenantRecord


class TestSchemaShape:
    def test_empty_schema_returns_empty_dict(self) -> None:
        # No per_tenant_config declared — return nothing rather than
        # leaking unknown keys from the raw JSONB.
        assert coerce_config({"locale": "en-GB"}, {}) == {}
        assert coerce_config({"locale": "en-GB"}, None) == {}

    def test_none_raw_returns_zero_values(self) -> None:
        # Tenants created before cycle 7 have config=NULL → coerce to
        # the schema's zero values rather than raising.
        result = coerce_config(
            None,
            {"locale": "str", "max_users": "int", "feature_billing": "bool"},
        )
        assert result == {"locale": "", "max_users": 0, "feature_billing": False}

    def test_unknown_keys_dropped(self) -> None:
        # Forward-compat: an old binary reading config written by a
        # newer one shouldn't crash on unknown keys.
        result = coerce_config(
            {"locale": "en-GB", "future_key": "garbage"},
            {"locale": "str"},
        )
        assert result == {"locale": "en-GB"}
        assert "future_key" not in result


class TestStrCoercion:
    def test_string_passthrough(self) -> None:
        assert coerce_config({"k": "abc"}, {"k": "str"}) == {"k": "abc"}

    def test_int_coerced_to_str(self) -> None:
        assert coerce_config({"k": 42}, {"k": "str"}) == {"k": "42"}

    def test_missing_key_zero(self) -> None:
        assert coerce_config({}, {"k": "str"}) == {"k": ""}

    def test_locale_treated_as_str(self) -> None:
        # `locale` is reserved for future BCP-47 normalisation; for
        # cycle 7 it shares storage with str.
        assert coerce_config({"l": "en-GB"}, {"l": "locale"}) == {"l": "en-GB"}


class TestIntCoercion:
    def test_int_passthrough(self) -> None:
        assert coerce_config({"n": 100}, {"n": "int"}) == {"n": 100}

    def test_string_int_coerced(self) -> None:
        assert coerce_config({"n": "42"}, {"n": "int"}) == {"n": 42}

    def test_invalid_int_falls_back_to_zero(self) -> None:
        # Tolerant of bad data — admin UI surfaces validation, not the
        # request path.
        assert coerce_config({"n": "not-a-number"}, {"n": "int"}) == {"n": 0}

    def test_bool_not_silently_coerced_to_int(self) -> None:
        # `int(True)` is 1 in Python; guard against the typo'd schema
        # case where a bool value lands in an int slot.
        assert coerce_config({"n": True}, {"n": "int"}) == {"n": 0}


class TestBoolCoercion:
    def test_bool_passthrough(self) -> None:
        assert coerce_config({"b": True}, {"b": "bool"}) == {"b": True}
        assert coerce_config({"b": False}, {"b": "bool"}) == {"b": False}

    def test_string_true_variants(self) -> None:
        for s in ("true", "TRUE", "True", "1", "yes", "on"):
            assert coerce_config({"b": s}, {"b": "bool"}) == {"b": True}, s

    def test_string_false_is_false(self) -> None:
        # The naive `bool("false")` returns True (non-empty string) —
        # this is exactly the trap the helper exists to avoid.
        assert coerce_config({"b": "false"}, {"b": "bool"}) == {"b": False}

    def test_other_strings_default_false(self) -> None:
        assert coerce_config({"b": "garbage"}, {"b": "bool"}) == {"b": False}

    def test_int_truthiness(self) -> None:
        assert coerce_config({"b": 1}, {"b": "bool"}) == {"b": True}
        assert coerce_config({"b": 0}, {"b": "bool"}) == {"b": False}


class TestUnknownDeclaredType:
    def test_unknown_type_falls_back_to_str(self) -> None:
        # Schema validation should reject this at link time, but if it
        # somehow slips through, we coerce as str rather than raising.
        assert coerce_config({"k": 42}, {"k": "uuid"}) == {"k": "42"}


class TestTenantRecord:
    def test_config_field_default_empty(self) -> None:
        # New TenantRecord field has a default — fixture / code paths
        # that don't set it explicitly should still work.
        record = TenantRecord(
            id="x",
            slug="acme",
            display_name="Acme",
            schema_name="tenant_acme",
            status="active",
            created_at="2026-05-01",
            updated_at="2026-05-01",
        )
        assert record.config == {}

    def test_config_field_in_dataclass(self) -> None:
        names = {f.name for f in fields(TenantRecord)}
        assert "config" in names

    def test_config_in_asdict(self) -> None:
        record = TenantRecord(
            id="x",
            slug="acme",
            display_name="Acme",
            schema_name="tenant_acme",
            status="active",
            created_at="2026-05-01",
            updated_at="2026-05-01",
            config={"locale": "en-GB"},
        )
        assert asdict(record)["config"] == {"locale": "en-GB"}
