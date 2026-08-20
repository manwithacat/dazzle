"""Gate: improve-cycle commit contract + leftover-token cadence (oral #127)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "improve_commit_contract.py"


def _load():
    name = "dazzle_scripts_improve_commit_contract"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _msg(
    subject: str,
    *,
    before: str = "CSV dumped 1200 as pounds.",
    after: str = "format_cell emits £12.00.",
    live: str = "invoice_ops list ?format=csv",
    extra: str = "",
) -> str:
    body = f"Before: {before}\nAfter: {after}\nLive: {live}"
    if extra:
        body += f"\n{extra}"
    return f"{subject}\n\n{body}\n"


def test_product_ship_with_labels_passes() -> None:
    mod = _load()
    text = _msg("improve: cycle 2253 framework-ux — CSV money export was raw pence, not £12.00")
    result = mod.check_message(text, ["src/dazzle/http/runtime/workspace_csv.py"])
    assert result.ok, result.errors


def test_empty_body_fails() -> None:
    mod = _load()
    text = "improve: cycle 2255 framework-ux — timeago naive UTC invented elapsed wall time\n"
    result = mod.check_message(text, ["src/dazzle/render/filters.py"])
    assert not result.ok
    assert any("empty" in e for e in result.errors)


def test_subject_overflow_fails() -> None:
    mod = _load()
    dumped = (
        "improve: cycle 2233 framework-ux — leftover-honest auth email must not invent "
        "sent theater Leftover email=zzz on magic-link; invite invented a persist."
    )
    result = mod.check_message(_msg(dumped), ["src/dazzle/http/runtime/auth/auth_views.py"])
    assert not result.ok
    joined = " ".join(result.errors)
    assert "leftover-honest" in joined or "sentences" in joined or "chars" in joined


def test_leftover_honest_param_subject_fails() -> None:
    mod = _load()
    text = _msg(
        "improve: cycle 2247 framework-ux — leftover-honest search ?entity= (oral #117)",
        before="?entity=zzz invented the unfiltered fleet.",
        after="leftover stays put (400).",
        live="contact_manager GET /_dazzle/search",
    )
    result = mod.check_message(text, ["src/dazzle/http/runtime/search_routes.py"])
    assert not result.ok
    assert any("leftover-honest" in e for e in result.errors)


def test_missing_live_fails() -> None:
    mod = _load()
    text = (
        "improve: cycle 2253 framework-ux — CSV money export was raw pence, not £12.00\n\n"
        "Before: dumped pence.\nAfter: £12.00.\n"
    )
    result = mod.check_message(text, ["src/dazzle/http/runtime/workspace_csv.py"])
    assert not result.ok
    assert any("Live" in e for e in result.errors)


def test_product_live_na_fails() -> None:
    mod = _load()
    text = _msg(
        "improve: cycle 2253 framework-ux — CSV money export was raw pence, not £12.00",
        live="n/a",
    )
    result = mod.check_message(text, ["src/dazzle/http/runtime/workspace_csv.py"])
    assert not result.ok
    assert any("Live" in e for e in result.errors)


def test_harness_only_self_audit_passes() -> None:
    mod = _load()
    text = _msg(
        "improve: cycle 2251 self-audit harness_only — leftover-token cadence (oral #121)",
        before="14 leftover-honest token ships claimed CLEAN.",
        after="audit CLEAN; next mutation is a different invent class.",
        live="n/a",
    )
    result = mod.check_message(
        text, [".claude/commands/improve/capability-map.md", "improve/oral-history.md"]
    )
    assert result.ok, result.errors


def test_self_audit_without_harness_only_fails() -> None:
    mod = _load()
    text = _msg(
        "improve: cycle 2251 self-audit — leftover-token cadence",
        live="n/a",
    )
    result = mod.check_message(text, ["improve/oral-history.md"])
    assert not result.ok
    assert any("harness_only" in e for e in result.errors)


def test_harness_only_with_src_fails() -> None:
    mod = _load()
    text = _msg(
        "improve: cycle 2253 framework-ux harness_only — CSV money export was raw pence",
        live="n/a",
    )
    result = mod.check_message(text, ["src/dazzle/http/runtime/workspace_csv.py"])
    assert not result.ok
    assert any("product paths" in e for e in result.errors)


def test_non_improve_subject_is_skipped() -> None:
    mod = _load()
    result = mod.check_message("feat: add hover docs for entity fields\n\nWhy: editors.\n")
    assert result.ok


def test_cadence_blocks_third_consecutive_leftover() -> None:
    mod = _load()
    subjects = [
        "improve: cycle 2250 framework-ux — leftover-honest file ?entity= (oral #120)",
        "improve: cycle 2249 framework-ux — leftover-honest connection group_map (oral #119)",
        "improve: cycle 2248 framework-ux — leftover-honest fragment ?source= (oral #118)",
        "improve: cycle 2247 framework-ux — leftover-honest search ?entity= (oral #117)",
    ]
    cad = mod.cadence_of(subjects)
    assert cad.consecutive == 4
    assert cad.blocked
    assert "consecutive" in cad.reason


def test_cadence_allows_two_consecutive_then_rotate() -> None:
    mod = _load()
    subjects = [
        "improve: cycle 2253 framework-ux — CSV money export was raw pence, not £12.00",
        "improve: cycle 2250 framework-ux — leftover-honest file ?entity= (oral #120)",
        "improve: cycle 2249 framework-ux — leftover-honest connection group_map (oral #119)",
    ]
    cad = mod.cadence_of(subjects)
    assert cad.consecutive == 0
    assert not cad.blocked


def test_cadence_counts_since_audit_not_across_it() -> None:
    mod = _load()
    subjects = [
        "improve: cycle 2253 framework-ux — leftover-honest search ?entity= (oral #117)",
        "improve: cycle 2251 self-audit harness_only — leftover-token cadence",
        "improve: cycle 2250 framework-ux — leftover-honest file ?entity= (oral #120)",
        "improve: cycle 2249 framework-ux — leftover-honest connection group_map (oral #119)",
    ]
    cad = mod.cadence_of(subjects)
    assert cad.since_audit == 1
    assert cad.consecutive == 1
    assert not cad.blocked


def test_cadence_blocks_fourth_leftover_since_audit() -> None:
    mod = _load()
    subjects = [
        "improve: cycle 2254 framework-ux — leftover-honest PatchOp op (oral #116)",
        "improve: cycle 2253 framework-ux — CSV money export was raw pence, not £12.00",
        "improve: cycle 2252 framework-ux — leftover-honest schemas (oral #114)",
        "improve: cycle 2251 framework-ux — leftover-honest groups (oral #115)",
        "improve: cycle 2250 framework-ux — leftover-honest file ?entity= (oral #120)",
        "improve: cycle 2240 self-audit harness_only — prior audit",
    ]
    cad = mod.cadence_of(subjects)
    assert cad.since_audit == 4
    assert cad.blocked
    assert "self-audit" in cad.reason


def test_cadence_skips_cimonitor_repair() -> None:
    mod = _load()
    subjects = [
        "improve: cycle 2234 cimonitor — leftover-honest auth email chrome-gate 400 vs 303",
        "improve: cycle 2233 framework-ux — leftover-honest auth email must not invent sent theater",
    ]
    cad = mod.cadence_of(subjects)
    assert cad.consecutive == 1
    assert not cad.blocked


def test_status_line_shape() -> None:
    mod = _load()
    cad = mod.Cadence(consecutive=0, since_audit=0, blocked=False)
    line = mod.format_status(cad)
    assert "leftover_token_streak=0/2" in line
    assert "since_audit=0/3" in line
    assert "blocked=0" in line
    assert "next_must_not=-" in line


def test_status_warns_at_cap_before_head_is_over() -> None:
    mod = _load()
    cad = mod.Cadence(consecutive=2, since_audit=2, blocked=False)
    line = mod.format_status(cad)
    assert "blocked=0" in line
    assert "next_must_not=leftover-token" in line


def test_policy_leftover_status_line_loads_with_dataclasses() -> None:
    """importlib load must register sys.modules or 3.14 dataclasses explode."""
    spec = importlib.util.spec_from_file_location(
        "dazzle_scripts_improve_policy_contract", REPO / "scripts" / "improve_policy.py"
    )
    assert spec is not None and spec.loader is not None
    pol = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = pol
    spec.loader.exec_module(pol)
    line = pol.leftover_token_status_line()
    assert line.startswith("leftover_token_streak=")


def test_cli_message_file(tmp_path: Path) -> None:
    mod = _load()
    path = tmp_path / "msg.txt"
    path.write_text(
        _msg("improve: cycle 2253 framework-ux — CSV money export was raw pence, not £12.00"),
        encoding="utf-8",
    )
    rc = mod.main(
        ["--message-file", str(path), "--paths", "src/dazzle/http/runtime/workspace_csv.py"]
    )
    assert rc == 0
