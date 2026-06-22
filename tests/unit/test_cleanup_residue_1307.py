"""Tests for #1307 — `dsl-run --cleanup` residue detection + test-data signature.

#1307: `--cleanup` reported `0 deleted, 1040 failed` (every teardown DELETE
404'd) while silently orphaning 752 rows the run had created. Two framework
fixes (the framework has NO persisted id-ledger — `_created_entities` is rebuilt
each run from live POST 2xx ids — so the orphans come from untracked ids the
tracked-id deletion can't reach):

1. A 404 at teardown is `absent` (already gone = success), not `failed`
   (covered in test_cleanup_cascade.py).
2. A SEPARATE post-cleanup residue scan (`detect_residue`) counts rows still
   present that bear this run's generated test-data signature — so an
   incomplete cleanup is loud, not silently masked by fix (1).

The signature (`is_generated_test_value`) lives beside the value generator in
`dazzle.core.field_values`; this file pins their parity so they can't drift.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dazzle.core.field_values import generate_field_value_from_str, is_generated_test_value
from dazzle.testing.test_runner import DazzleClient


@pytest.fixture
def client() -> DazzleClient:
    return DazzleClient(api_url="http://localhost:8000", ui_url="http://localhost:3000")


class TestSignatureParity:
    """`is_generated_test_value` must recognise what the generator emits."""

    @pytest.mark.parametrize(
        "name,ftype",
        [
            ("title", "str"),
            ("title", "str(200)"),
            ("description", "text"),
            ("email", "email"),
            ("attachment", "file"),
            ("notes", "unknowntype"),  # falls to the `test_<name>` branch
        ],
    )
    def test_generated_values_are_recognised(self, name: str, ftype: str) -> None:
        value = generate_field_value_from_str(name, ftype, unique=True)
        assert is_generated_test_value(value), (
            f"generator emitted {value!r} for ({name}, {ftype}) but the residue "
            f"detector doesn't recognise it — signature drift (#1307)."
        )

    def test_truncated_str_still_recognised(self) -> None:
        """A short max_length truncates the value but keeps the 'Test ' prefix."""
        value = generate_field_value_from_str("t", "str", max_length=10)
        assert value.startswith("Test ")
        assert is_generated_test_value(value)

    @pytest.mark.parametrize(
        "value",
        [
            "Acme Corporation",  # real company name
            "jane.doe@gmail.com",  # real email, not @example.com
            "active",  # enum value
            "2026-05-31",  # date
            42,  # non-string
            None,
            "",
        ],
    )
    def test_real_values_not_misclassified(self, value: object) -> None:
        """High precision: production data must not be flagged as test residue."""
        assert not is_generated_test_value(value)


class TestDetectResidue:
    """`detect_residue` counts marker-bearing rows per type, queries the API."""

    def test_counts_only_marker_rows(self, client: DazzleClient) -> None:
        """Rows bearing a generated signature count; real rows don't."""
        rows = [
            {"id": "1", "title": "Test title_abc123"},  # test residue
            {"id": "2", "name": "Acme Corp"},  # real row
            {"id": "3", "email": "test_ff00@example.com"},  # test residue
        ]
        client.entities.get_entities = MagicMock(return_value=rows)  # type: ignore[method-assign]

        residue = client.cleanup.detect_residue(["Contact"])
        assert residue == {"Contact": 2}

    def test_clean_type_absent_from_report(self, client: DazzleClient) -> None:
        """A type with zero residue is omitted (residue report stays terse)."""
        client.entities.get_entities = MagicMock(return_value=[{"id": "1", "name": "Real"}])  # type: ignore[method-assign]
        assert client.cleanup.detect_residue(["Contact"]) == {}

    def test_per_type_query_failure_is_skipped(self, client: DazzleClient) -> None:
        """A failing list query for one type doesn't abort the whole scan."""

        def _flaky(entity_name: str) -> list[dict[str, object]]:
            if entity_name == "Bad":
                raise RuntimeError("boom")
            return [{"id": "1", "title": "Test title_x"}]

        client.entities.get_entities = MagicMock(side_effect=_flaky)  # type: ignore[method-assign]
        residue = client.cleanup.detect_residue(["Bad", "Contact"])
        assert residue == {"Contact": 1}

    def test_empty_types_no_queries(self, client: DazzleClient) -> None:
        client.entities.get_entities = MagicMock(return_value=[])  # type: ignore[method-assign]
        assert client.cleanup.detect_residue([]) == {}
        client.entities.get_entities.assert_not_called()
