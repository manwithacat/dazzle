"""Drift gate for the framework UX-maturity rubric (docs/reference/ux-maturity.md).

Each criterion carries a declared capability level (the version-pinned baseline)
plus a probe against the framework's own IR/registry/renderer. A probe that
contradicts its declared level is drift — a primitive shipped (level should rise)
or regressed (fell). Keeping this green keeps the scorecard honest.
"""

from dazzle.qa.ux_maturity import CRITERIA, PRINCIPLES, drift_violations, run_scan


def test_no_drift_baseline_in_sync() -> None:
    violations = drift_violations()
    assert violations == [], "ux-maturity baseline drift:\n" + "\n".join(violations)


def test_scan_shape_well_formed() -> None:
    sc = run_scan()
    assert sc["framework_version"]
    assert 0.0 <= sc["overall_index"] <= 4.0
    assert sc["rag"] in {"red", "amber", "green"}
    assert set(sc["principles"]) == set(PRINCIPLES)
    assert set(sc["criteria"]) == {c.id for c in CRITERIA}
    # every criterion is assigned to a known principle and a 0-4 level
    for c in sc["criteria"].values():
        assert c["principle"] in PRINCIPLES
        assert c["capability"] in {0, 1, 2, 3, 4}
        assert c["rag"] in {"red", "amber", "green"}


def test_principle_indices_match_member_means() -> None:
    sc = run_scan()
    for pdata in sc["principles"].values():
        levels = [sc["criteria"][cid]["capability"] for cid in pdata["criteria"]]
        assert abs(pdata["index"] - sum(levels) / len(levels)) < 1e-6


def test_backlog_is_amber_or_red_only_and_leverage_ordered() -> None:
    sc = run_scan()
    backlog = sc["framework_backlog"]
    # only red/amber criteria (level <= 2) appear
    assert all(b["level"] <= 2 for b in backlog)
    # high-leverage gaps come first
    order = {"high": 0, "medium": 1, "low": 2}
    keys = [order.get(b["leverage"], 3) for b in backlog]
    assert keys == sorted(keys)
    # the known top gaps are present and high-leverage. 1a left the backlog when
    # `display: auto` became the default (#1492 default-flip → level 3); 1b left
    # when the declared `semantic:` binding became render-consumed (#1493 slice 2),
    # reaching level 4 with WCAG colour+icon+text + state-machine-terminal inference.
    # 3d stays a gap: #1494 shipped the `when_empty:` *vocabulary* (opt-in), but the
    # level-4 adaptive auto-default is deferred (it tripped the fleet's
    # viewport/interaction gates) — so the data-right default isn't there yet.
    high = {b["criterion"] for b in backlog if b["leverage"] == "high"}
    assert {"1c", "3d"} <= high
    not_gaps = {b["criterion"] for b in backlog}
    assert "1a" not in not_gaps  # level 3, no longer a gap
    assert "1b" not in not_gaps  # level 4 (#1493 slice 2 complete), no longer a gap


def test_criteria_count_and_ids() -> None:
    # 13 criteria after the R1-R5 revisions (3b split; 3e added)
    assert len(CRITERIA) == 13
    ids = {c.id for c in CRITERIA}
    assert {"3b", "3c", "3e"} <= ids  # role/state split + scope concealment
