"""Tests for runtime parameter IR types."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dazzle.core.ir.params import ParamConstraints, ParamRef, ParamSpec


class TestParamConstraints:
    """Tests for ParamConstraints model."""

    def test_construction_defaults(self) -> None:
        c = ParamConstraints()
        assert c.min_value is None
        assert c.max_value is None
        assert c.min_length is None
        assert c.max_length is None
        assert c.ordered is None
        assert c.range is None
        assert c.enum_values is None
        assert c.pattern is None

    def test_construction_with_values(self) -> None:
        c = ParamConstraints(
            min_value=0.0,
            max_value=100.0,
            min_length=1,
            max_length=255,
            ordered="ascending",
            range=[0.0, 10.0],
            enum_values=["a", "b", "c"],
            pattern=r"^\d+$",
        )
        assert c.min_value == 0.0
        assert c.max_value == 100.0
        assert c.min_length == 1
        assert c.max_length == 255
        assert c.ordered == "ascending"
        assert c.range == [0.0, 10.0]
        assert c.enum_values == ["a", "b", "c"]
        assert c.pattern == r"^\d+$"

    def test_frozen(self) -> None:
        c = ParamConstraints(min_value=1.0)
        with pytest.raises(ValidationError):
            c.min_value = 2.0  # type: ignore[misc]


class TestParamSpec:
    """Tests for ParamSpec model."""

    def test_construction_minimal(self) -> None:
        p = ParamSpec(key="max_retries", param_type="int", default=3, scope="system")
        assert p.key == "max_retries"
        assert p.param_type == "int"
        assert p.default == 3
        assert p.scope == "system"
        assert p.constraints is None
        assert p.description is None
        assert p.category is None
        assert p.depends_on == []
        assert p.sensitive is False

    def test_construction_all_fields(self) -> None:
        constraints = ParamConstraints(min_value=1, max_value=10)
        p = ParamSpec(
            key="page_size",
            param_type="int",
            default=25,
            scope="tenant",
            constraints=constraints,
            description="Number of items per page",
            category="pagination",
            depends_on=["feature_pagination"],
            sensitive=False,
        )
        assert p.key == "page_size"
        assert p.scope == "tenant"
        assert p.constraints is not None
        assert p.constraints.min_value == 1
        assert p.description == "Number of items per page"
        assert p.category == "pagination"
        assert p.depends_on == ["feature_pagination"]

    def test_scope_values(self) -> None:
        for scope in ("system", "tenant", "user"):
            p = ParamSpec(key="k", param_type="str", default="", scope=scope)  # type: ignore[arg-type]
            assert p.scope == scope

    def test_scope_invalid(self) -> None:
        with pytest.raises(ValidationError):
            ParamSpec(key="k", param_type="str", default="", scope="invalid")  # type: ignore[arg-type]

    def test_json_round_trip(self) -> None:
        constraints = ParamConstraints(min_value=0, max_value=100, pattern=r"^\w+$")
        original = ParamSpec(
            key="threshold",
            param_type="float",
            default=0.5,
            scope="tenant",
            constraints=constraints,
            description="Alert threshold",
            category="alerts",
            depends_on=["alerts_enabled"],
            sensitive=True,
        )
        json_str = original.model_dump_json()
        restored = ParamSpec.model_validate_json(json_str)
        assert restored == original
        assert restored.constraints is not None
        assert restored.constraints.pattern == r"^\w+$"
        assert restored.sensitive is True

    def test_frozen(self) -> None:
        p = ParamSpec(key="k", param_type="int", default=1, scope="system")
        with pytest.raises(ValidationError):
            p.key = "other"  # type: ignore[misc]

    def test_default_can_be_any_type(self) -> None:
        # int default
        p1 = ParamSpec(key="k1", param_type="int", default=42, scope="system")
        assert p1.default == 42
        # str default
        p2 = ParamSpec(key="k2", param_type="str", default="hello", scope="system")
        assert p2.default == "hello"
        # list default
        p3 = ParamSpec(key="k3", param_type="list[float]", default=[1.0, 2.0], scope="system")
        assert p3.default == [1.0, 2.0]
        # bool default
        p4 = ParamSpec(key="k4", param_type="bool", default=False, scope="system")
        assert p4.default is False
        # json default
        p5 = ParamSpec(key="k5", param_type="json", default={"a": 1}, scope="system")
        assert p5.default == {"a": 1}


class TestParamRef:
    """Tests for ParamRef model."""

    def test_construction(self) -> None:
        r = ParamRef(key="max_retries", param_type="int", default=3)
        assert r.key == "max_retries"
        assert r.param_type == "int"
        assert r.default == 3

    def test_frozen(self) -> None:
        r = ParamRef(key="k", param_type="str", default="v")
        with pytest.raises(ValidationError):
            r.key = "other"  # type: ignore[misc]

    def test_json_round_trip(self) -> None:
        original = ParamRef(key="timeout", param_type="float", default=30.0)
        restored = ParamRef.model_validate_json(original.model_dump_json())
        assert restored == original


class TestParamSpecInAppSpec:
    """Tests for ParamSpec integration with AppSpec and ModuleFragment."""

    def test_appspec_params_default_empty(self) -> None:
        from dazzle.core.ir.appspec import AppSpec
        from dazzle.core.ir.domain import DomainSpec

        app = AppSpec(name="test", domain=DomainSpec(entities=[]))
        assert app.params == []

    def test_module_fragment_params_default_empty(self) -> None:
        from dazzle.core.ir.module import ModuleFragment

        frag = ModuleFragment()
        assert frag.params == []

    def test_appspec_with_params(self) -> None:
        from dazzle.core.ir.appspec import AppSpec
        from dazzle.core.ir.domain import DomainSpec

        p = ParamSpec(key="max_retries", param_type="int", default=3, scope="system")
        app = AppSpec(name="test", domain=DomainSpec(entities=[]), params=[p])
        assert len(app.params) == 1
        assert app.params[0].key == "max_retries"

    def test_exports_from_ir_package(self) -> None:
        from dazzle.core.ir import ParamConstraints as PC
        from dazzle.core.ir import ParamRef as PR
        from dazzle.core.ir import ParamSpec as PS

        assert PC is ParamConstraints
        assert PR is ParamRef
        assert PS is ParamSpec
