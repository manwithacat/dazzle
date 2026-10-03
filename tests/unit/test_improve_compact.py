"""`scripts/improve_compact.py` — the driver's state compaction.

This script owns the invariant "settled rows leave the working backlog", which
is what keeps the file under the 100 KB threshold SKILL.md documents. It had
**one** test, for the log half, and the first attempt at headerless-table support
shipped a bug that rewrote the real 154 KB backlog into 3.2 MB of verbatim
repeats (`for i, line in enumerate(...)` discards a reassigned `i`, so the run
handler re-entered its own run). These tests are the reason the second attempt is
safe.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "improve_compact.py"


def _load() -> Any:
    name = "dazzle_scripts_improve_compact"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ic = _load()

HEADERED = """# Improve Backlog

## Lane: framework-ux

| id | component | status | notes |
|----|-----------|--------|-------|
| FX-1 | card chrome | DONE | shipped |
| FX-2 | toast | PENDING | next |
"""

# The shape the example-apps lane actually accumulated: no header row, status
# first, ~360 rows. Header-driven parsing skips these entirely.
HEADERLESS = """## Lane: example-apps

| DONE | #2377 | cycle 2377: eval hub |
| DONE | #2379 | cycle 2379: empty-list title |
| PENDING | #2410-seed | next campaign |
| PENDING | #2411-seed | another |
"""


_SYNTHETIC_HEADER = {"| status | ref | notes |", "|---|---|---|"}


def _archived(archived: dict[str, list[str]]) -> list[str]:
    """Archived rows, without the synthetic header the script adds per bucket."""
    return [row for rows in archived.values() for row in rows if row not in _SYNTHETIC_HEADER]


# --- headered tables ---------------------------------------------------------


def test_headered_settled_row_archives_and_pending_stays() -> None:
    kept, archived = ic.compact_backlog(HEADERED, closed_issues=set())

    assert "FX-1" not in kept
    assert "FX-2" in kept
    assert any("FX-1" in row for row in _archived(archived))


# --- headerless, status-first tables -----------------------------------------


def test_headerless_status_first_rows_archive() -> None:
    """61 settled rows in this shape were permanently unarchivable."""
    kept, archived = ic.compact_backlog(HEADERLESS, closed_issues=set())

    assert "#2377" not in kept and "#2379" not in kept
    assert "#2410-seed" in kept and "#2411-seed" in kept
    assert len(_archived(archived)) == 2


def test_output_contains_no_duplicated_rows() -> None:
    """The regression that shipped: a re-entered run re-appended its own lines,
    turning 163 distinct rows into 11,049."""
    text = "\n".join([HEADERED, HEADERLESS])
    kept, archived = ic.compact_backlog(text, closed_issues=set())

    everything = [line for line in kept.splitlines() if line.startswith("|")]
    everything += _archived(archived)
    data_rows = [r for r in everything if not set(r) <= set("|- ") and "status" not in r]
    assert len(data_rows) == len(set(data_rows)), "a row was emitted twice"


def test_compaction_is_idempotent() -> None:
    text = "\n".join([HEADERED, HEADERLESS])
    once, archived_once = ic.compact_backlog(text, closed_issues=set())
    twice, archived_twice = ic.compact_backlog(once, closed_issues=set())

    assert twice == once
    assert _archived(archived_twice) == []


def test_a_mixed_run_claims_only_its_status_shaped_rows() -> None:
    """The example-apps section had a second, differently-shaped table appended
    below the headerless one with no separator between them."""
    mixed = (
        HEADERLESS + "| AUD-022 | self-audit | DONE | 1 |\n| AUD-021 | self-audit | DONE | 1 |\n"
    )
    kept, archived = ic.compact_backlog(mixed, closed_issues=set())

    assert "#2377" not in kept
    assert "AUD-022" in kept, "a differently-shaped row must be left for the headered path"
    assert len(_archived(archived)) == 2


def test_prose_led_rows_are_never_claimed() -> None:
    """Fail-safe: if the first cell is not status-shaped, nothing is claimed."""
    prose = "## Lane: example-apps\n\n| some prose | not a status |\n| more prose | here |\n"
    kept, archived = ic.compact_backlog(prose, closed_issues=set())

    assert archived == {}
    assert "some prose" in kept


def test_a_lane_with_no_archive_statuses_is_untouched() -> None:
    """A lane missing from ARCHIVE_STATUSES keeps every row — which is how the
    hm-convergence lane's 160 DONE rows became permanent until it was added."""
    lane = "## Lane: mystery-lane\n\n| DONE | #1 | x |\n| DONE | #2 | y |\n"
    kept, archived = ic.compact_backlog(lane, closed_issues=set())

    assert archived == {}
    assert "#1" in kept


def test_every_lane_in_the_backlog_has_a_compaction_policy() -> None:
    """The hm-convergence omission, as a standing check: a lane the driver knows
    about but the compactor does not can never shed a settled row."""
    backlog = REPO / "dev_docs" / "improve-backlog.md"
    if not backlog.exists():
        return
    import re

    lanes = set(re.findall(r"^## Lane: (.+?)\s*$", backlog.read_text(encoding="utf-8"), re.M))
    missing = sorted(lanes - set(ic.ARCHIVE_STATUSES))
    assert not missing, f"lanes with no compaction policy: {missing}"


# --- the log half (verbatim from the original single test) --------------------------
def test_compact_log_keeps_highest_cycle_ids_when_file_order_is_mixed() -> None:
    """compact_log must keep highest cycle ids, not the file-order tail.

    Tip cycles prepended, then an older sweep mid-file — do not archive the tip.
    """
    blocks = []
    for n in list(range(2079, 2069, -1)) + list(range(2045, 2045 + ic.KEEP_CYCLES)):
        blocks.append(f"## Cycle {n} — 2026-08-14 — lane: example-apps — outcome: PASS\n- c{n}\n")
    text = "\n" + "\n".join(blocks)
    kept, archived = ic.compact_log(text)

    assert "## Cycle 2079" in kept
    assert "## Cycle 2070" in kept
    assert "## Cycle 2045" in archived
    assert "## Cycle 2079" not in archived
    assert kept.index("## Cycle 2079") < kept.index("## Cycle 2070")
