#!/usr/bin/env python3
"""Score Dazzle example apps on agent-cognition sophistication axes.

Usage (repo root):
  .venv/bin/python docs/research/scripts/example_sophistication.py
  .venv/bin/python docs/research/scripts/example_sophistication.py --json

Axes favour multi-persona RBAC, lifecycles with transitions, processes,
and stories over bare entity count. Used as the evaluation substrate for
agent-prior experiments (see docs/research/agent-domain-prior-investigation.md).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "examples"
SKIP_PARTS = frozenset(
    {
        "build",
        "site",
        "screenshots",
        "dev_docs",
        "fixtures",
        "tests",
        "app",
        "services",
        "templates",
        "docs",
        "node_modules",
    }
)


def _dsl_text(ex: Path) -> str:
    parts: list[str] = []
    for p in sorted(ex.rglob("*.dsl")):
        if SKIP_PARTS.intersection(p.parts):
            continue
        parts.append(p.read_text(errors="replace"))
    return "\n".join(parts)


def _entity_blocks(text: str) -> dict[str, str]:
    """Map entity name → body (best-effort; next entity or EOF)."""
    out: dict[str, str] = {}
    matches = list(re.finditer(r"^entity\s+(\w+)\b", text, re.M))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[m.group(1)] = text[start:end]
    return out


def score_example(ex: Path) -> dict:
    text = _dsl_text(ex)
    entities = _entity_blocks(text)
    personas = sorted(set(re.findall(r"^persona\s+(\w+)", text, re.M)))
    stories = sorted(set(re.findall(r"^story\s+(\S+)", text, re.M)))
    processes = sorted(set(re.findall(r"^process\s+(\w+)", text, re.M)))
    workspaces = sorted(set(re.findall(r"^workspace\s+(\w+)", text, re.M)))

    status_with_trans: list[str] = []
    status_no_trans: list[str] = []
    status_detail: dict[str, list[str]] = {}
    with_invariant: list[str] = []
    with_scope: list[str] = []
    with_permit: list[str] = []
    with_lifecycle_block: list[str] = []

    for name, body in entities.items():
        status = re.search(r"status:\s*enum\[([^\]]+)\]", body)
        has_trans = bool(re.search(r"^\s*transitions:", body, re.M))
        has_life = bool(re.search(r"^\s*lifecycle:", body, re.M))
        has_inv = bool(re.search(r"^\s*invariant:", body, re.M))
        has_scope = bool(re.search(r"^\s*scope:", body, re.M))
        has_permit = bool(re.search(r"^\s*permit:", body, re.M))
        if status:
            states = [s.strip() for s in status.group(1).split(",")]
            status_detail[name] = states
            if has_trans or has_life:
                status_with_trans.append(name)
            else:
                status_no_trans.append(name)
        if has_inv:
            with_invariant.append(name)
        if has_scope:
            with_scope.append(name)
        if has_permit:
            with_permit.append(name)
        if has_life:
            with_lifecycle_block.append(name)

    n_entities = len(entities)
    n_personas = len(personas)
    n_stories = len(stories)
    n_processes = len(processes)
    n_workspaces = len(workspaces)
    scope_blocks = len(re.findall(r"^\s*scope:", text, re.M))
    permit_blocks = len(re.findall(r"^\s*permit:", text, re.M))
    llm = len(re.findall(r"llm_intent|llm_config", text))
    rhythms = len(re.findall(r"^rhythm\s+", text, re.M))
    experiences = len(re.findall(r"^experience\s+", text, re.M))
    poly = len(re.findall(r"poly_ref", text))
    ledgers = len(re.findall(r"^ledger\s+", text, re.M))

    has_agent_domain = (ex / "AGENT_DOMAIN.md").exists()
    has_stems = (ex / "stems").is_dir()
    has_trial = (ex / "trial.toml").exists()

    # Weighted for agent-authored SaaS density, not raw entity count.
    score = (
        n_entities * 1
        + n_personas * 3
        + n_stories * 2
        + n_processes * 4
        + n_workspaces * 2
        + min(scope_blocks, 20) * 2
        + min(permit_blocks, 20) * 1
        + len(with_invariant) * 2
        + len(status_with_trans) * 4
        + len(status_no_trans) * (-1)  # incomplete lifecycle is a deficit
        + llm * 3
        + rhythms * 3
        + experiences * 3
        + poly * 2
        + ledgers * 3
        + (2 if has_agent_domain else 0)
        + (2 if has_stems else 0)
        + (1 if has_trial else 0)
    )

    multi_persona_no_process = n_personas >= 3 and n_processes == 0

    return {
        "example": ex.name,
        "score": score,
        "n_entities": n_entities,
        "n_personas": n_personas,
        "n_stories": n_stories,
        "n_processes": n_processes,
        "n_workspaces": n_workspaces,
        "entities": sorted(entities),
        "personas": personas,
        "processes": processes,
        "workspaces": workspaces,
        "status_with_transitions": status_with_trans,
        "status_without_transitions": status_no_trans,
        "status_detail": status_detail,
        "entities_with_invariant": with_invariant,
        "entities_with_scope": with_scope,
        "lifecycle_blocks": with_lifecycle_block,
        "scope_blocks": scope_blocks,
        "permit_blocks": permit_blocks,
        "multi_persona_no_process": multi_persona_no_process,
        "has_agent_domain": has_agent_domain,
        "has_stems": has_stems,
        "has_trial": has_trial,
    }


def score_all() -> list[dict]:
    rows: list[dict] = []
    for d in sorted(EXAMPLES.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if not any(d.rglob("*.dsl")):
            continue
        rows.append(score_example(d))
    rows.sort(key=lambda r: -r["score"])
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    args = ap.parse_args()
    rows = score_all()
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    print(f"{'example':22} {'sc':>4} ent per sto pro ws  +trans -trans mpp")
    for r in rows:
        mpp = "Y" if r["multi_persona_no_process"] else "."
        print(
            f"{r['example']:22} {r['score']:4} "
            f"{r['n_entities']:3} {r['n_personas']:3} {r['n_stories']:3} "
            f"{r['n_processes']:3} {r['n_workspaces']:2}  "
            f"{len(r['status_with_transitions']):2}     "
            f"{len(r['status_without_transitions']):2}    {mpp}"
        )
    print()
    print("mpp = multi-persona (≥3) with zero process blocks")
    print("+trans / -trans = status enums with / without transitions|lifecycle")
    gaps = [r for r in rows if r["status_without_transitions"] or r["multi_persona_no_process"]]
    if gaps:
        print("\nGaps:")
        for r in gaps:
            bits = []
            if r["status_without_transitions"]:
                bits.append(f"status∄trans={r['status_without_transitions']}")
            if r["multi_persona_no_process"]:
                bits.append("≥3persona∄process")
            print(f"  {r['example']}: {'; '.join(bits)}")


if __name__ == "__main__":
    main()
