"""
Tests for the ``tenant_config.<key>`` condition vocabulary (#1324 FR-4 slice A).

A nav ``when:`` condition referencing ``tenant_config.<key>`` resolves the
value from ``context["tenant_config"]`` at evaluation time. A bare flag
(``when: tenant_config.mis_connected``) parses to an implicit truthy
``= true`` comparison and evaluates truthy/falsy. Roles/grants/current_user
resolution stays unchanged.
"""

from dazzle.core.condition_eval import evaluate_condition


def _tenant_flag(key: str) -> dict:
    """The shape parse_condition_expr emits for a bare ``tenant_config.<key>``
    reference: an implicit ``= true`` truthy comparison."""
    return {
        "comparison": {
            "field": f"tenant_config.{key}",
            "operator": "=",
            "value": {"literal": True},
        }
    }


class TestTenantConfigResolution:
    def test_flag_truthy_when_present_and_true(self) -> None:
        cond = _tenant_flag("mis_connected")
        ctx = {"tenant_config": {"mis_connected": True}}
        assert evaluate_condition(cond, {}, ctx) is True

    def test_flag_false_when_present_and_false(self) -> None:
        cond = _tenant_flag("mis_connected")
        ctx = {"tenant_config": {"mis_connected": False}}
        assert evaluate_condition(cond, {}, ctx) is False

    def test_flag_false_when_absent(self) -> None:
        cond = _tenant_flag("mis_connected")
        ctx = {"tenant_config": {}}
        assert evaluate_condition(cond, {}, ctx) is False

    def test_flag_false_when_no_tenant_config_namespace(self) -> None:
        cond = _tenant_flag("mis_connected")
        assert evaluate_condition(cond, {}, {}) is False

    def test_explicit_equality_against_string_value(self) -> None:
        cond = {
            "comparison": {
                "field": "tenant_config.tier",
                "operator": "=",
                "value": {"literal": "pro"},
            }
        }
        assert evaluate_condition(cond, {}, {"tenant_config": {"tier": "pro"}}) is True
        assert evaluate_condition(cond, {}, {"tenant_config": {"tier": "free"}}) is False

    def test_tenant_config_does_not_shadow_record_field(self) -> None:
        """A plain field (no ``tenant_config.`` prefix) still resolves from the
        record, unaffected by the new namespace."""
        cond = {
            "comparison": {
                "field": "status",
                "operator": "=",
                "value": {"literal": "active"},
            }
        }
        assert evaluate_condition(cond, {"status": "active"}, {"tenant_config": {}}) is True


class TestRolesAndGrantsUnchanged:
    def test_role_check_still_works(self) -> None:
        cond = {"role_check": {"role_name": "admin"}}
        assert evaluate_condition(cond, {}, {"user_roles": ["admin"]}) is True
        assert evaluate_condition(cond, {}, {"user_roles": ["viewer"]}) is False

    def test_compound_role_and_tenant_flag(self) -> None:
        cond = {
            "operator": "and",
            "left": {"role_check": {"role_name": "admin"}},
            "right": _tenant_flag("mis_connected"),
        }
        ctx = {"user_roles": ["admin"], "tenant_config": {"mis_connected": True}}
        assert evaluate_condition(cond, {}, ctx) is True
        ctx_off = {"user_roles": ["admin"], "tenant_config": {"mis_connected": False}}
        assert evaluate_condition(cond, {}, ctx_off) is False
