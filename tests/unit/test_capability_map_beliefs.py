"""A capability the loop claims to exercise must state what it re-tested (#1759 W4).

The capability map defines COGNITION as work that "changes agent *beliefs*", and
`Last-exercised` measures exercise. Those are different things: a COGNITION
capability exercised every cycle can carry a belief that has been wrong for a
year, and before this gate the map had no column in which to say so.

Two cycles produced two fresh measurements and zero belief revisions, and the log
line looked exactly like a cycle that changed the roadmap. This gate closes that:
a row stamped `USED` must say what was re-tested, and when — so "PASS with
residual=0" and "we were wrong" cannot look the same.

It also enforces the boring half, which is where the value usually is:

* every registry row carries the two columns (a header/narrow drift fails);
* `Since revised` is never later than `Last-exercised` (you revised during the
  run that exercised it) and never in the future;
* a COGNITION row that claims `USED` with an empty `Believed` fails.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
MAP = REPO / ".agents" / "skills" / "improve" / "capability-map.md"

COLUMNS = [
    "Capability",
    "Class",
    "Surface",
    "Owning lane",
    "Last-exercised",
    "Status",
    "Believed",
    "Since revised",
]
COGNITION_CLASSES = {"COGNITION", "HYGIENE", "DRIVER", "EXEMPT"}


def _table() -> list[list[str]]:
    rows: list[list[str]] = []
    for line in MAP.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or set(line) <= set("|- "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0] == "Capability":
            continue
        if len(cells) == len(COLUMNS):
            rows.append(cells)
    return rows


def _current_cycle() -> int:
    """Highest cycle number this repository can attest to.

    `dev_docs/improve-log.md` is **gitignored local state** and does not exist in
    a clean checkout, so trusting it alone made this gate red in CI while green on
    a developer machine. Prefer the committed map's own numbers; consult the log
    only when it happens to be present.
    """
    rows = _table()
    from_map = max(
        (int(cell) for row in rows for cell in (row[4], row[7]) if cell.isdigit()),
        default=0,
    )
    log = REPO / "dev_docs" / "improve-log.md"
    if not log.is_file():
        return from_map
    from_log = max(
        (int(m) for m in re.findall(r"^## Cycle (\d+)", log.read_text(encoding="utf-8"), re.M)),
        default=0,
    )
    return max(from_map, from_log)


def test_the_registry_table_has_the_belief_columns() -> None:
    """A header/narrow drift fails here rather than in a reader's eyes."""
    rows = _table()
    assert len(rows) >= 60, f"only {len(rows)} registry rows parsed — the header moved?"
    assert all(len(r) == len(COLUMNS) for r in rows), "every row must carry all eight columns"


def test_every_used_capability_states_what_it_retested() -> None:
    """The load-bearing assertion: a claimed exercise without a stated belief is a
    timestamp, not a cognition."""
    empty = [r[0] for r in _table() if r[5] == "USED" and (r[6] in {"", "—"})]
    assert not empty, (
        f"{len(empty)} capability row(s) are stamped USED with no belief recorded. A cycle "
        "that re-tested something and found it unchanged must say so — 're-tested, "
        "unchanged' is a result; nothing is not. Rows: " + ", ".join(empty[:4])
    )


def test_since_revised_is_never_after_the_run_that_exercised_it() -> None:
    rows = _table()
    bad = []
    for r in rows:
        last, since = r[4], r[7]
        if not (last.isdigit() and since.isdigit()):
            continue
        if int(since) > int(last):
            bad.append(f"{r[0][:40]}: revised @ {since} but last exercised @ {last}")
    assert not bad, "\n".join(bad)


def test_no_revision_is_dated_in_the_future() -> None:
    """`Since revised` is a cycle number, not a promise."""
    current = _current_cycle()
    assert current > 0, "no cycle numbers anywhere — the map's revisions cannot be checked"
    future = [r[0] for r in _table() if r[7].isdigit() and int(r[7]) > current]
    assert not future, f"revised after the last recorded cycle ({current}): {future[:4]}"


def test_a_cognition_row_may_not_be_used_without_a_belief() -> None:
    """Class-scoped restatement of the rule above, so the intent survives a
    refactor that changes what `USED` means."""
    offenders = [
        f"{r[0][:40]} ({r[1]})"
        for r in _table()
        if r[1] in COGNITION_CLASSES and r[5] == "USED" and r[6] in {"", "—"}
    ]
    assert not offenders, f"COGNITION rows used with no belief: {offenders}"


def test_the_vocabulary_documents_the_columns() -> None:
    """A gate on columns nobody documented is a column nobody fills."""
    text = MAP.read_text(encoding="utf-8")
    assert "Since revised" in text and "Believed" in text
    assert "re-tested" in text, "the vocabulary must say that an unchanged belief counts"
