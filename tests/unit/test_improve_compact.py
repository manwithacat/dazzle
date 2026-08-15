"""compact_log must keep highest cycle ids, not the file-order tail."""

from scripts.improve_compact import KEEP_CYCLES, compact_log


def test_compact_log_keeps_highest_cycle_ids_when_file_order_is_mixed() -> None:
    """Tip cycles prepended, then an older sweep mid-file — do not archive the tip."""
    blocks = []
    # Newest-first tip, then an older contiguous sweep (the 2045-in-the-middle shape).
    for n in list(range(2079, 2069, -1)) + list(range(2045, 2045 + KEEP_CYCLES)):
        blocks.append(f"## Cycle {n} — 2026-08-14 — lane: example-apps — outcome: PASS\n- c{n}\n")
    text = "\n" + "\n".join(blocks)
    kept, archived = compact_log(text)
    assert "## Cycle 2079" in kept
    assert "## Cycle 2070" in kept
    assert "## Cycle 2045" in archived
    assert "## Cycle 2079" not in archived
    assert kept.index("## Cycle 2079") < kept.index("## Cycle 2070")
