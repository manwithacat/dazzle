"""Tests for the subagent-explore backlog ingestion writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_explore import (
    SubagentExploreFindings,
)
from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_ingest import (
    PersonaRun,
    ingest_findings,
)

# Minimal backlog fixture: just enough structure for the ingestion writer
# to find its insertion points. Real backlog has many more tables above
# and hand-written narrative in the header — we don't exercise those.
_MINIMAL_BACKLOG = """\
# UX Cycle Backlog

## Components

| id | component | status |
|----|-----------|--------|
| UX-001 | dashboard-grid | DONE |

## Exploration Findings

| id     | kind                | description                                                | status    | source_cycle | notes |
|--------|---------------------|------------------------------------------------------------|-----------|--------------|-------|
| EX-001 | coverage-gap        | 82 template files still contain DaisyUI class tokens.      | OPEN      | 17           | seed  |

## Proposed Components

| id      | component_name | description                                              | status    | source_cycle | notes |
|---------|----------------|----------------------------------------------------------|-----------|--------------|-------|
| PROP-037 | workspace-detail-drawer | Permanently-mounted drawer. | PROPOSED | 198 | seed |
"""


def _make_findings(
    *,
    proposals: list[dict[str, object]] | None = None,
    observations: list[dict[str, object]] | None = None,
) -> SubagentExploreFindings:
    data = {
        "proposals": proposals or [],
        "observations": observations or [],
    }
    return SubagentExploreFindings.from_dict(data)


@pytest.fixture
def backlog_file(tmp_path: Path) -> Path:
    path = tmp_path / "ux-backlog.md"
    path.write_text(_MINIMAL_BACKLOG)
    return path


class TestIdAllocation:
    def test_next_prop_id_starts_after_highest_existing(self, backlog_file: Path) -> None:
        run = PersonaRun(
            persona_id="agent",
            run_id="20260415-030000",
            app_name="support_tickets",
            findings=_make_findings(
                proposals=[
                    {
                        "component_name": "kanban-board",
                        "description": "horizontally-scrolling column board",
                        "observed_on_page": "/app/workspaces/ticket_queue",
                        "selector_hint": "div.flex.gap-3",
                    }
                ]
            ),
        )
        result = ingest_findings(backlog_file, cycle_number=199, runs=[run])
        assert result.prop_rows_added == 1
        assert result.starting_prop_id == 38  # existing highest is PROP-037
        text = backlog_file.read_text()
        assert "| PROP-038 | kanban-board |" in text

    def test_next_ex_id_starts_after_highest_existing(self, backlog_file: Path) -> None:
        run = PersonaRun(
            persona_id="agent",
            run_id="20260415-030000",
            app_name="support_tickets",
            findings=_make_findings(
                observations=[
                    {
                        "page": "/app/ticket",
                        "note": "Empty state has no CTA",
                        "severity": "notable",
                    }
                ]
            ),
        )
        result = ingest_findings(backlog_file, cycle_number=199, runs=[run])
        assert result.ex_rows_added == 1
        assert result.starting_ex_id == 2  # existing highest is EX-001
        text = backlog_file.read_text()
        assert "| EX-002 |" in text


class TestDeduplication:
    def test_proposal_skipped_if_component_name_already_in_backlog(
        self, backlog_file: Path
    ) -> None:
        run = PersonaRun(
            persona_id="user",
            run_id="20260415-030000",
            app_name="contact_manager",
            findings=_make_findings(
                proposals=[
                    {
                        "component_name": "workspace-detail-drawer",  # already PROP-037
                        "description": "duplicate attempt",
                    }
                ]
            ),
        )
        result = ingest_findings(backlog_file, cycle_number=199, runs=[run])
        assert result.prop_rows_added == 0
        assert result.proposals_skipped_as_duplicates == ["workspace-detail-drawer"]

    def test_dedup_is_scoped_within_a_single_ingest_call(self, backlog_file: Path) -> None:
        """Two runs in the same call that both propose the same component
        get one PROP row for the first and a dedup-skip for the second."""
        finding = {"component_name": "kanban-board", "description": "d"}
        runs = [
            PersonaRun(
                persona_id="agent",
                run_id="run-a",
                app_name="support_tickets",
                findings=_make_findings(proposals=[finding]),
            ),
            PersonaRun(
                persona_id="customer",
                run_id="run-b",
                app_name="support_tickets",
                findings=_make_findings(proposals=[finding]),
            ),
        ]
        result = ingest_findings(backlog_file, cycle_number=199, runs=runs)
        assert result.prop_rows_added == 1
        assert result.proposals_skipped_as_duplicates == ["kanban-board"]


class TestRowFormatting:
    def test_prop_row_carries_cycle_persona_and_run_id_in_notes(self, backlog_file: Path) -> None:
        run = PersonaRun(
            persona_id="manager",
            run_id="20260415-030259",
            app_name="support_tickets",
            findings=_make_findings(
                proposals=[
                    {
                        "component_name": "bulk-action-bar",
                        "description": "pinned destructive-action bar",
                        "observed_on_page": "/app/ticket",
                        "selector_hint": "div.has-delete",
                    }
                ]
            ),
        )
        ingest_findings(backlog_file, cycle_number=199, runs=[run])
        row = next(
            line for line in backlog_file.read_text().splitlines() if "bulk-action-bar" in line
        )
        assert "Cycle 199" in row
        assert "support_tickets/manager" in row
        assert "20260415-030259" in row
        assert "`/app/ticket`" in row
        assert "`div.has-delete`" in row

    def test_ex_row_includes_severity_and_page(self, backlog_file: Path) -> None:
        run = PersonaRun(
            persona_id="customer",
            run_id="run-b",
            app_name="support_tickets",
            findings=_make_findings(
                observations=[
                    {
                        "page": "/app/workspaces/my_tickets",
                        "note": "403 on nav links",
                        "severity": "concerning",
                    }
                ]
            ),
        )
        ingest_findings(backlog_file, cycle_number=199, runs=[run])
        row = next(line for line in backlog_file.read_text().splitlines() if "concerning" in line)
        assert "severity=concerning" in row
        assert "`/app/workspaces/my_tickets`" in row
        assert "403 on nav links" in row

    def test_newlines_in_descriptions_are_flattened(self, backlog_file: Path) -> None:
        run = PersonaRun(
            persona_id="agent",
            run_id="run-a",
            app_name="support_tickets",
            findings=_make_findings(
                proposals=[
                    {
                        "component_name": "multi-line-widget",
                        "description": "line one\nline two\n\nline three",
                    }
                ]
            ),
        )
        ingest_findings(backlog_file, cycle_number=199, runs=[run])
        text = backlog_file.read_text()
        assert "line one line two line three" in text
        # The row is still a single line (no embedded newlines that
        # would break the markdown table)
        row_lines = [line for line in text.splitlines() if "multi-line-widget" in line]
        assert len(row_lines) == 1

    def test_pipe_characters_in_cells_are_escaped(self, backlog_file: Path) -> None:
        run = PersonaRun(
            persona_id="agent",
            run_id="run-a",
            app_name="support_tickets",
            findings=_make_findings(
                proposals=[
                    {
                        "component_name": "pipey-thing",
                        "description": "uses `a | b` syntax internally",
                    }
                ]
            ),
        )
        ingest_findings(backlog_file, cycle_number=199, runs=[run])
        row = next(line for line in backlog_file.read_text().splitlines() if "pipey-thing" in line)
        # The description's pipe is escaped so it doesn't split the row
        assert r"a \| b" in row


class TestIdempotencyAndEmptyInputs:
    def test_empty_runs_list_writes_nothing(self, backlog_file: Path) -> None:
        original = backlog_file.read_text()
        result = ingest_findings(backlog_file, cycle_number=199, runs=[])
        assert result.prop_rows_added == 0
        assert result.ex_rows_added == 0
        assert backlog_file.read_text() == original

    def test_runs_with_only_observations_leave_prop_table_unchanged(
        self, backlog_file: Path
    ) -> None:
        run = PersonaRun(
            persona_id="agent",
            run_id="run-a",
            app_name="support_tickets",
            findings=_make_findings(observations=[{"note": "something", "severity": "minor"}]),
        )
        original_prop_section = backlog_file.read_text().split("## Proposed Components")[1]
        result = ingest_findings(backlog_file, cycle_number=199, runs=[run])
        assert result.prop_rows_added == 0
        assert result.ex_rows_added == 1
        new_prop_section = backlog_file.read_text().split("## Proposed Components")[1]
        assert new_prop_section == original_prop_section

    def test_proposal_with_no_component_name_is_dropped_with_warning(
        self, backlog_file: Path
    ) -> None:
        run = PersonaRun(
            persona_id="agent",
            run_id="run-a",
            app_name="support_tickets",
            findings=_make_findings(proposals=[{"description": "no name"}]),
        )
        result = ingest_findings(backlog_file, cycle_number=199, runs=[run])
        assert result.prop_rows_added == 0
        assert any("no component_name" in w for w in result.warnings)


class TestInsertionLocation:
    def test_new_prop_rows_go_at_end_of_proposed_components_table(self, backlog_file: Path) -> None:
        run = PersonaRun(
            persona_id="agent",
            run_id="run-a",
            app_name="support_tickets",
            findings=_make_findings(
                proposals=[{"component_name": "new-widget", "description": "d"}]
            ),
        )
        ingest_findings(backlog_file, cycle_number=199, runs=[run])
        text = backlog_file.read_text()
        # The new row comes after PROP-037 (the pre-existing last row)
        prop_037_pos = text.index("PROP-037")
        prop_038_pos = text.index("PROP-038")
        assert prop_038_pos > prop_037_pos

    def test_insertion_preserves_unrelated_sections(self, backlog_file: Path) -> None:
        run = PersonaRun(
            persona_id="agent",
            run_id="run-a",
            app_name="support_tickets",
            findings=_make_findings(
                proposals=[{"component_name": "new-widget", "description": "d"}],
                observations=[{"note": "o", "severity": "minor"}],
            ),
        )
        ingest_findings(backlog_file, cycle_number=199, runs=[run])
        text = backlog_file.read_text()
        # The unrelated Components section stays intact
        assert "| UX-001 | dashboard-grid | DONE |" in text
        # The existing PROP-037 stays intact
        assert "| PROP-037 | workspace-detail-drawer |" in text
        # And so does EX-001
        assert "| EX-001 | coverage-gap" in text
