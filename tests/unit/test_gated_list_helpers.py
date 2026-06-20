"""#1422 follow-on: unit-lock the helper seams extracted from `gated_list`
(CC 37 → 10). The end-to-end scope/permit behaviour is covered by the PG oracle
(`test_scope_runtime_pg.py`) and the list-handler suite; these tests pin the pure
helpers so the decomposition can't silently drift.
"""

from datetime import date
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.access.gated import (
    InvalidTemporalParam,
    _parse_temporal_filters,
    _resolve_list_scope,
    access_context_from,
)


def _service_with_temporal(as_of_param: str = "as_of", end_field: str = "valid_to"):
    temporal = SimpleNamespace(as_of_param=as_of_param, end_field=end_field)
    return SimpleNamespace(entity_spec=SimpleNamespace(temporal=temporal))


class TestParseTemporalFilters:
    def test_non_temporal_entity_returns_empty(self):
        service = SimpleNamespace(entity_spec=SimpleNamespace(temporal=None))
        assert (
            _parse_temporal_filters(
                service, temporal_as_of_raw="2026-01-01", temporal_include_closed=True
            )
            == {}
        )

    def test_missing_entity_spec_returns_empty(self):
        service = SimpleNamespace()  # no entity_spec attr
        assert (
            _parse_temporal_filters(
                service, temporal_as_of_raw="2026-01-01", temporal_include_closed=False
            )
            == {}
        )

    def test_valid_as_of_parses_to_date_key(self):
        out = _parse_temporal_filters(
            _service_with_temporal(), temporal_as_of_raw="2026-06-20", temporal_include_closed=False
        )
        assert out == {"__as_of": date(2026, 6, 20)}

    def test_include_closed_sets_end_isnull_false(self):
        out = _parse_temporal_filters(
            _service_with_temporal(end_field="closed_at"),
            temporal_as_of_raw=None,
            temporal_include_closed=True,
        )
        assert out == {"closed_at__isnull": False}

    def test_malformed_as_of_raises_invalid_temporal_param(self):
        # The #1406 ordering guard: this raises only AFTER permit+scope in gated_list.
        with pytest.raises(InvalidTemporalParam) as exc:
            _parse_temporal_filters(
                _service_with_temporal(as_of_param="as_of"),
                temporal_as_of_raw="not-a-date",
                temporal_include_closed=False,
            )
        assert "as_of" in str(exc.value)


class TestResolveListScope:
    def _access(self, cedar):
        return access_context_from(
            auth_context=SimpleNamespace(is_authenticated=True),
            entity_name="Widget",
            cedar_access_spec=cedar,
            fk_graph=None,
            admin_personas=None,
        )

    def test_no_cedar_returns_filters_unchanged(self):
        access = self._access(cedar=None)
        sql = {"a": 1}
        assert (
            _resolve_list_scope(
                access, is_authenticated=True, user_id="u1", ref_targets=None, sql_filters=sql
            )
            is sql
        )

    def test_unauthenticated_returns_filters_unchanged(self):
        access = self._access(cedar=SimpleNamespace(scopes={}))
        sql = {"a": 1}
        assert (
            _resolve_list_scope(
                access, is_authenticated=False, user_id=None, ref_targets=None, sql_filters=sql
            )
            is sql
        )

    def test_cedar_without_scopes_returns_filters_unchanged(self):
        access = self._access(cedar=SimpleNamespace(scopes=None))
        sql = {"a": 1}
        assert (
            _resolve_list_scope(
                access, is_authenticated=True, user_id="u1", ref_targets=None, sql_filters=sql
            )
            is sql
        )
