"""Tests for runtime parameter store and resolver."""

from typing import Any

import pytest

from dazzle.core.ir.params import ParamConstraints, ParamRef, ParamSpec


def _spec(
    key: str = "k",
    param_type: str = "int",
    default: Any = 0,
    scope: str = "system",
    constraints: ParamConstraints | None = None,
) -> ParamSpec:
    return ParamSpec(
        key=key, param_type=param_type, default=default, scope=scope, constraints=constraints
    )


# ---------------------------------------------------------------------------
# validate_param_value
# ---------------------------------------------------------------------------


class TestValidateParamValue:
    def test_int_passes(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        assert validate_param_value(_spec(param_type="int"), 42) == []

    def test_int_rejects_bool(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        errors = validate_param_value(_spec(param_type="int"), True)
        assert errors

    def test_int_rejects_str(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        errors = validate_param_value(_spec(param_type="int"), "hello")
        assert errors

    def test_float_accepts_int(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        assert validate_param_value(_spec(param_type="float"), 3) == []

    def test_float_accepts_float(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        assert validate_param_value(_spec(param_type="float"), 3.14) == []

    def test_bool_passes(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        assert validate_param_value(_spec(param_type="bool"), True) == []
        assert validate_param_value(_spec(param_type="bool"), False) == []

    def test_bool_rejects_int(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        errors = validate_param_value(_spec(param_type="bool"), 0)
        assert errors

    def test_str_passes(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        assert validate_param_value(_spec(param_type="str"), "hello") == []

    def test_list_float_type(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        assert validate_param_value(_spec(param_type="list[float]"), [1.0, 2, 3.5]) == []
        errors = validate_param_value(_spec(param_type="list[float]"), [1, "x"])
        assert errors

    def test_list_str_type(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        assert validate_param_value(_spec(param_type="list[str]"), ["a", "b"]) == []
        errors = validate_param_value(_spec(param_type="list[str]"), ["a", 1])
        assert errors

    def test_min_max_value(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        c = ParamConstraints(min_value=0, max_value=100)
        spec = _spec(param_type="int", constraints=c)
        assert validate_param_value(spec, 50) == []
        assert validate_param_value(spec, -1) != []
        assert validate_param_value(spec, 101) != []

    def test_min_max_length(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        c = ParamConstraints(min_length=2, max_length=4)
        spec = _spec(param_type="list[float]", default=[], constraints=c)
        assert validate_param_value(spec, [1.0, 2.0]) == []
        assert validate_param_value(spec, [1.0]) != []
        assert validate_param_value(spec, [1.0, 2.0, 3.0, 4.0, 5.0]) != []

    def test_ordered_ascending(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        c = ParamConstraints(ordered="ascending")
        spec = _spec(param_type="list[float]", default=[], constraints=c)
        assert validate_param_value(spec, [1.0, 2.0, 3.0]) == []
        assert validate_param_value(spec, [3.0, 1.0]) != []

    def test_ordered_descending(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        c = ParamConstraints(ordered="descending")
        spec = _spec(param_type="list[float]", default=[], constraints=c)
        assert validate_param_value(spec, [3.0, 2.0, 1.0]) == []
        assert validate_param_value(spec, [1.0, 3.0]) != []

    def test_range_constraint(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        c = ParamConstraints(range=[0.0, 1.0])
        spec = _spec(param_type="list[float]", default=[], constraints=c)
        assert validate_param_value(spec, [0.0, 0.5, 1.0]) == []
        assert validate_param_value(spec, [0.0, 1.5]) != []

    def test_valid_returns_empty(self) -> None:
        from dazzle_back.runtime.param_store import validate_param_value

        assert validate_param_value(_spec(param_type="int"), 10) == []


# ---------------------------------------------------------------------------
# ParamResolver
# ---------------------------------------------------------------------------


class TestParamResolver:
    def test_resolve_default(self) -> None:
        from dazzle_back.runtime.param_store import ParamResolver

        specs = {"k": _spec(default=42)}
        r = ParamResolver(specs)
        val, src = r.resolve("k")
        assert val == 42
        assert src == "default"

    def test_resolve_tenant_override(self) -> None:
        from dazzle_back.runtime.param_store import ParamResolver

        specs = {"k": _spec(default=42)}
        r = ParamResolver(specs, overrides={("k", "tenant", "t1"): 99})
        val, src = r.resolve("k", tenant_id="t1")
        assert val == 99
        assert src == "tenant/t1"

    def test_resolve_cascade_user_over_tenant(self) -> None:
        from dazzle_back.runtime.param_store import ParamResolver

        specs = {"k": _spec(default=0)}
        r = ParamResolver(
            specs,
            overrides={
                ("k", "tenant", "t1"): 10,
                ("k", "user", "u1"): 20,
            },
        )
        val, src = r.resolve("k", tenant_id="t1", user_id="u1")
        assert val == 20
        assert src == "user/u1"

    def test_resolve_cascade_system(self) -> None:
        from dazzle_back.runtime.param_store import ParamResolver

        specs = {"k": _spec(default=0)}
        r = ParamResolver(specs, overrides={("k", "system", "system"): 77})
        val, src = r.resolve("k")
        assert val == 77
        assert src == "system"

    def test_resolve_cascade_full(self) -> None:
        """user > tenant > system > default."""
        from dazzle_back.runtime.param_store import ParamResolver

        specs = {"k": _spec(default=0)}
        overrides = {
            ("k", "system", "system"): 1,
            ("k", "tenant", "t1"): 2,
            ("k", "user", "u1"): 3,
        }
        r = ParamResolver(specs, overrides=overrides)
        # All present → user wins
        val, src = r.resolve("k", tenant_id="t1", user_id="u1")
        assert val == 3 and src == "user/u1"
        # No user → tenant wins
        val, src = r.resolve("k", tenant_id="t1")
        assert val == 2 and src == "tenant/t1"
        # No user, no tenant → system wins
        val, src = r.resolve("k")
        assert val == 1 and src == "system"

    def test_resolve_unknown_key_raises(self) -> None:
        from dazzle_back.runtime.param_store import ParamResolver

        r = ParamResolver({})
        with pytest.raises(KeyError):
            r.resolve("missing")

    def test_set_override_validates(self) -> None:
        from dazzle_back.runtime.param_store import ParamResolver

        specs = {"k": _spec(param_type="int", default=0)}
        r = ParamResolver(specs)
        errors = r.set_override("k", "system", "system", 10)
        assert errors == []
        val, src = r.resolve("k")
        assert val == 10

    def test_set_override_rejects_invalid(self) -> None:
        from dazzle_back.runtime.param_store import ParamResolver

        specs = {"k": _spec(param_type="int", default=0)}
        r = ParamResolver(specs)
        errors = r.set_override("k", "system", "system", "bad")
        assert errors


# ---------------------------------------------------------------------------
# resolve_value
# ---------------------------------------------------------------------------


class TestResolveValue:
    def test_passthrough_literal(self) -> None:
        from dazzle_back.runtime.param_store import resolve_value

        assert resolve_value(42, None) == 42
        assert resolve_value("hello", None) == "hello"

    def test_resolves_param_ref(self) -> None:
        from dazzle_back.runtime.param_store import ParamResolver, resolve_value

        ref = ParamRef(key="k", param_type="int", default=5)
        specs = {"k": _spec(default=5)}
        r = ParamResolver(specs, overrides={("k", "system", "system"): 99})
        assert resolve_value(ref, r) == 99

    def test_param_ref_default_when_no_resolver(self) -> None:
        from dazzle_back.runtime.param_store import resolve_value

        ref = ParamRef(key="k", param_type="int", default=5)
        assert resolve_value(ref, None) == 5
