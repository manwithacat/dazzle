"""Drift gate for the counter-prior catalogue.

Asserts that every `docs/counter-priors/*.md` file (a) has valid YAML
frontmatter conforming to the CounterPrior schema, (b) contains the four
mandatory body sections, (c) has an id matching its filename, (d) is
listed in INDEX.md, and (e) is round-trippable into the loader without
errors. Layer-3 net for the markdown catalogue.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.mcp.semantics_kb.counter_priors import (
    REQUIRED_SECTIONS,
    CounterPriorParseError,
    counter_priors_dir,
    load_all_counter_priors,
    load_counter_prior,
)

pytestmark = pytest.mark.gate

CATALOGUE = counter_priors_dir()


def _entry_files() -> list[Path]:
    return [p for p in sorted(CATALOGUE.glob("*.md")) if p.name not in ("INDEX.md", "README.md")]


@pytest.mark.parametrize("path", _entry_files(), ids=lambda p: p.name)
def test_every_entry_parses(path: Path) -> None:
    """Each entry's frontmatter and body must be well-formed."""
    entry = load_counter_prior(path)

    assert entry.id, f"{path.name}: id is empty"
    assert entry.name, f"{path.name}: name is empty"
    assert entry.layer in ("grammar", "inference", "filter")
    assert entry.summary.strip(), f"{path.name}: summary is empty"
    assert entry.triggers_text or entry.triggers_code, (
        f"{path.name}: must declare at least one trigger (text or code)"
    )

    expected_id = path.stem.replace("-", "_")
    assert entry.id == expected_id, (
        f"{path.name}: id {entry.id!r} does not match filename {expected_id!r}"
    )


@pytest.mark.parametrize("path", _entry_files(), ids=lambda p: p.name)
def test_every_entry_has_required_sections(path: Path) -> None:
    """The four mandatory body sections must all be present."""
    entry = load_counter_prior(path)
    for section in REQUIRED_SECTIONS:
        assert section in entry.body, f"{path.name}: missing required section {section!r}"


def test_load_all_returns_every_entry() -> None:
    """The directory walker picks up every entry file."""
    entries = load_all_counter_priors()
    entry_files = _entry_files()
    assert len(entries) == len(entry_files), (
        f"load_all returned {len(entries)} entries but {len(entry_files)} files exist"
    )
    loaded_ids = {e.id for e in entries}
    file_ids = {p.stem.replace("-", "_") for p in entry_files}
    assert loaded_ids == file_ids


def test_index_lists_every_entry() -> None:
    """INDEX.md must reference every entry by its filename."""
    index_path = CATALOGUE / "INDEX.md"
    assert index_path.exists(), "INDEX.md missing from catalogue directory"
    index_text = index_path.read_text()
    for path in _entry_files():
        assert path.name in index_text, (
            f"{path.name} not listed in INDEX.md — add a row under '## Active entries'"
        )


def test_malformed_frontmatter_rejected(tmp_path: Path) -> None:
    """A file with broken frontmatter raises CounterPriorParseError."""
    bad = tmp_path / "bad.md"
    bad.write_text("no frontmatter at all\n\n## The corpus prior\n")
    with pytest.raises(CounterPriorParseError):
        load_counter_prior(bad)


def test_missing_sections_rejected(tmp_path: Path) -> None:
    """A file missing a required section raises CounterPriorParseError."""
    incomplete = tmp_path / "incomplete.md"
    incomplete.write_text(
        "---\n"
        "id: incomplete\n"
        "name: Incomplete\n"
        "layer: inference\n"
        "summary: missing sections\n"
        "triggers_text: [foo]\n"
        "---\n\n"
        "# Incomplete\n\n"
        "## The corpus prior\n\nstuff\n"
        # missing the other three sections
    )
    with pytest.raises(CounterPriorParseError, match="missing required sections"):
        load_counter_prior(incomplete)


def test_id_mismatch_rejected(tmp_path: Path) -> None:
    """Frontmatter id must match filename."""
    mismatched = tmp_path / "right-name.md"
    mismatched.write_text(
        "---\n"
        "id: wrong_name\n"
        "name: Mismatched\n"
        "layer: inference\n"
        "summary: id != filename\n"
        "triggers_text: [x]\n"
        "---\n\n"
        "## The corpus prior\n\n## Wrong shape\n\n## Right shape\n\n## Why this matters here\n"
    )
    with pytest.raises(CounterPriorParseError, match="does not match filename"):
        load_counter_prior(mismatched)


def test_invalid_regex_in_triggers_code_rejected(tmp_path: Path) -> None:
    """triggers_code patterns must compile."""
    bad_regex = tmp_path / "bad_regex.md"
    bad_regex.write_text(
        "---\n"
        "id: bad_regex\n"
        "name: Bad regex\n"
        "layer: inference\n"
        "summary: regex test\n"
        "triggers_text: []\n"
        "triggers_code: ['[unclosed']\n"
        "---\n\n"
        "## The corpus prior\n\n## Wrong shape\n\n## Right shape\n\n## Why this matters here\n"
    )
    with pytest.raises(CounterPriorParseError, match="invalid regex"):
        load_counter_prior(bad_regex)


# ─────────────────────────────────────────────────────────────────────────
# Cross-catalogue parity with inference_kb.toml modeling_guidance
# ─────────────────────────────────────────────────────────────────────────


def _modeling_guidance_anti_pattern_ids() -> set[str]:
    """Return every modeling_guidance id that carries an `anti_pattern` field.

    These are the antipattern shapes that #1249's `_propose_patterns` used to
    source from TOML. After Phase 3 unification (2026-05-25) `_propose_patterns`
    sources from counter-priors instead, but the TOML rows remain for the
    `lookup_inference` MCP path. The two surfaces must not drift apart: every
    TOML anti_pattern needs a matching counter-prior so the antipattern
    catalogue is consistent across both consumers.
    """
    import tomllib

    kb_path = Path(__file__).resolve().parents[2] / "src" / "dazzle" / "mcp" / "inference_kb.toml"
    data = tomllib.loads(kb_path.read_text())
    return {
        entry["id"]
        for entry in data.get("modeling_guidance", [])
        if isinstance(entry, dict) and entry.get("anti_pattern") and entry.get("id")
    }


# Map from TOML modeling_guidance id → counter-prior id. The counter-prior
# catalogue uses cleaner names (no "_antipattern" suffix on every entry); this
# map encodes the translation so future renames are explicit.
_KB_TO_COUNTER_PRIOR = {
    "no_polymorphic_keys": "polymorphic_associations",
    "subtype_of_only_for_true_isa": "subtype_polymorphism_default",
    "polymorphic_association_antipattern": "polymorphic_associations",
    "no_god_entities": "god_entities",
    "prefer_soft_delete_keyword": "hand_rolled_soft_delete",
    "no_stringly_refs": "stringly_typed_refs",
    "prefer_temporal_keyword": "hand_rolled_temporal",
    "no_duplicated_fields": "duplicated_parent_fields",
}


def test_every_kb_anti_pattern_has_counter_prior() -> None:
    """Every modeling_guidance anti_pattern in TOML must have a counter-prior
    in markdown. Adding a new anti_pattern field to TOML without a matching
    markdown file is drift."""
    kb_ids = _modeling_guidance_anti_pattern_ids()
    counter_prior_ids = {e.id for e in load_all_counter_priors()}

    missing = []
    for kb_id in kb_ids:
        target = _KB_TO_COUNTER_PRIOR.get(kb_id)
        if target is None:
            missing.append(
                f"{kb_id}: no entry in _KB_TO_COUNTER_PRIOR map — "
                "add the mapping when introducing a new modeling_guidance "
                "anti_pattern, and write the matching counter-prior markdown."
            )
            continue
        if target not in counter_prior_ids:
            missing.append(
                f"{kb_id} → {target}: target counter-prior not found at "
                f"docs/counter-priors/{target.replace('_', '-')}.md"
            )

    assert not missing, "modeling_guidance ↔ counter-prior drift:\n" + "\n".join(missing)


def test_kb_to_counter_prior_map_is_total() -> None:
    """Every TOML anti_pattern id must appear in the translation map.
    Otherwise the parity test above can pass while still missing entries."""
    kb_ids = _modeling_guidance_anti_pattern_ids()
    unmapped = kb_ids - set(_KB_TO_COUNTER_PRIOR.keys())
    assert not unmapped, (
        f"modeling_guidance ids missing from _KB_TO_COUNTER_PRIOR: {unmapped}. "
        "Add the mapping when introducing a new modeling_guidance anti_pattern."
    )


# ─────────────────────────────────────────────────────────────────────────
# Counter-prior ↔ Sentinel heuristic drift (PA-LLM-07 onwards)
# ─────────────────────────────────────────────────────────────────────────


def _python_audit_heuristic_ids() -> set[str]:
    """Return every heuristic_id declared on PythonAuditAgent.

    Reflection is sufficient: heuristics are discovered the same way at runtime.
    """
    from dazzle.sentinel.agents.python_audit import PythonAuditAgent

    agent = PythonAuditAgent()
    return {meta.heuristic_id for meta, _ in agent.get_heuristics()}


def test_every_declared_detector_resolves() -> None:
    """Every detector id declared in a counter-prior frontmatter must exist."""
    heuristic_ids = _python_audit_heuristic_ids()
    missing: list[str] = []
    for entry in load_all_counter_priors():
        for detector in entry.detectors:
            if detector.agent == "PA" and detector.id not in heuristic_ids:
                missing.append(
                    f"{entry.id}: declared detector {detector.id!r} not found on PythonAuditAgent"
                )
    assert not missing, "Detector ids declared in catalogue but not implemented:\n" + "\n".join(
        missing
    )


def test_exceptions_entry_declares_pa_llm_07() -> None:
    """Sanity pin: the pilot entry must wire to PA-LLM-07."""
    entries = {e.id: e for e in load_all_counter_priors()}
    entry = entries["exceptions_as_control_flow"]
    detector_ids = {d.id for d in entry.detectors}
    assert "PA-LLM-07" in detector_ids
