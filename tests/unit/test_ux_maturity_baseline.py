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
    # reaching level 4 with WCAG colour+icon+text + state-machine-terminal inference;
    # 3d left when `when_empty:` + the resolve_when_empty default-flip shipped — an
    # empty supporting region self-collapses to header-only by default (#1494, level 4),
    # with the geometry-gate skip + added-card exemption keeping the auto-default safe;
    # 1c left when an unset metrics tile began inferring a default comparison delta
    # (#1491 resolve_comparison → level 3); 3a left when heading action prominence
    # became inferred (#1491 resolve_action_prominence → level 3); 2d left when
    # auto-derived columns began inferring field economy (#1491
    # resolve_column_economy → level 3). **MILESTONE: with 2d gone the backlog is
    # EMPTY — every one of the 13 criteria now clears the L3 bar.**
    assert backlog == [], f"expected an empty backlog (all criteria >= L3), got {backlog}"


def test_criteria_count_and_ids() -> None:
    # 13 criteria after the R1-R5 revisions (3b split; 3e added)
    assert len(CRITERIA) == 13
    ids = {c.id for c in CRITERIA}
    assert {"3b", "3c", "3e"} <= ids  # role/state split + scope concealment
