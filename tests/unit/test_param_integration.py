"""Tests for runtime parameter integration (#572 Task 5).

Covers:
- _dazzle_params migration table creation (mock DB)
- resolve_value with literal passthrough
- resolve_value with ParamRef resolving to default when no override
- Static heatmap thresholds (no ParamRef) still work in workspace rendering
"""

from unittest.mock import MagicMock

from dazzle.core.ir.params import ParamRef, ParamSpec
from dazzle.http.runtime.param_store import ParamResolver, resolve_value

# ---------------------------------------------------------------------------
# resolve_value tests
# ---------------------------------------------------------------------------


class TestResolveValueLiteral:
    """resolve_value with literal (non-ParamRef) values passes through."""

    def test_string(self) -> None:
        assert resolve_value("hello", None) == "hello"

    def test_list(self) -> None:
        assert resolve_value([0.25, 0.5, 0.75], None) == [0.25, 0.5, 0.75]

    def test_none(self) -> None:
        assert resolve_value(None, None) is None

    def test_int(self) -> None:
        assert resolve_value(42, None) == 42


class TestResolveValueParamRef:
    """resolve_value with ParamRef resolves to default when no override."""

    def test_default_no_resolver(self) -> None:
        ref = ParamRef(key="threshold", param_type="float", default=0.5)
        assert resolve_value(ref, None) == 0.5

    def test_default_with_resolver(self) -> None:
        spec = ParamSpec(key="threshold", param_type="float", default=0.5, scope="system")
        resolver = ParamResolver(specs={"threshold": spec})
        ref = ParamRef(key="threshold", param_type="float", default=0.5)
        result = resolve_value(ref, resolver, tenant_id=None)
        assert result == 0.5

    def test_override_returned(self) -> None:
        spec = ParamSpec(key="threshold", param_type="float", default=0.5, scope="system")
        resolver = ParamResolver(
            specs={"threshold": spec},
            overrides={("threshold", "system", "system"): 0.9},
        )
        ref = ParamRef(key="threshold", param_type="float", default=0.5)
        result = resolve_value(ref, resolver, tenant_id=None)
        assert result == 0.9

    def test_list_default_no_resolver(self) -> None:
        ref = ParamRef(key="heat_thresh", param_type="list[float]", default=[0.3, 0.6, 0.9])
        assert resolve_value(ref, None) == [0.3, 0.6, 0.9]


# ---------------------------------------------------------------------------
# ensure_dazzle_params_table tests
# ---------------------------------------------------------------------------


class TestEnsureDazzleParamsTable:
    """Migration function creates _dazzle_params table (mock DB)."""

    def test_creates_table(self) -> None:
        from dazzle.http.runtime.migrations import ensure_dazzle_params_table

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_db = MagicMock()
        mock_db.connection.return_value = mock_conn

        ensure_dazzle_params_table(mock_db)

        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS _dazzle_params" in sql
        assert "key TEXT NOT NULL" in sql
        assert "scope TEXT NOT NULL" in sql
        assert "value_json" in sql
        assert "PRIMARY KEY" in sql
