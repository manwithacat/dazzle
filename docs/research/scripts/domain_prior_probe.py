#!/usr/bin/env python3
"""Probe agent domain-analysis tools against example briefs.

Compares:
  - domain extract (AGENT_DOMAIN path)
  - identify_lifecycles attachment to grounded nouns
  - gold DSL status/transitions

Usage (repo root):
  .venv/bin/python docs/research/scripts/domain_prior_probe.py
  .venv/bin/python docs/research/scripts/domain_prior_probe.py --example invoice_ops
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _gold_status_entities(ex: Path) -> dict[str, dict]:
    text = ""
    for p in ex.rglob("*.dsl"):
        if "build" in p.parts:
            continue
        text += "\n" + p.read_text(errors="replace")
    out: dict[str, dict] = {}
    matches = list(re.finditer(r"^entity\s+(\w+)\b", text, re.M))
    for i, m in enumerate(matches):
        name = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        status = re.search(r"status:\s*enum\[([^\]]+)\]", body)
        if not status:
            continue
        out[name] = {
            "states": [s.strip() for s in status.group(1).split(",")],
            "has_transitions": bool(re.search(r"^\s*transitions:", body, re.M)),
            "has_lifecycle": bool(re.search(r"^\s*lifecycle:", body, re.M)),
        }
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def probe(ex: Path) -> dict:
    from dazzle.domain_brief.extract import extract_from_path, find_founder_brief

    brief = find_founder_brief(ex)
    if brief is None:
        for c in ("SPECIFICATION.md", "SPEC.md", "AGENT_DOMAIN.md"):
            if (ex / c).exists() and c != "AGENT_DOMAIN.md":
                brief = ex / c
                break
    if brief is None:
        return {"example": ex.name, "error": "no brief"}

    ad = extract_from_path(brief)
    nouns = {
        n.name: {
            "lifecycle_hint": list(n.lifecycle_hint),
            "owner_field_hint": n.owner_field_hint,
            "status": n.status,
        }
        for n in ad.nouns
    }
    personas = [
        {
            "id": p.id_hint,
            "stable": p.stable_id_candidate,
            "status": p.status,
        }
        for p in ad.personas
    ]
    gold = _gold_status_entities(ex)

    # Lifecycle attachment: does any grounded noun carry a lifecycle that
    # fuzzy-matches a gold status entity?
    gold_norms = {_norm(k): k for k in gold}
    lifecycle_on_gold = []
    lifecycle_orphan = []
    for n, meta in nouns.items():
        if not meta["lifecycle_hint"]:
            continue
        nn = _norm(n)
        hit = None
        for gn, gname in gold_norms.items():
            if nn == gn or nn in gn or gn in nn:
                hit = gname
                break
        if hit:
            lifecycle_on_gold.append({"noun": n, "gold": hit, "hint": meta["lifecycle_hint"]})
        else:
            lifecycle_orphan.append({"noun": n, "hint": meta["lifecycle_hint"]})

    gold_missing_hint = []
    for gname, gmeta in gold.items():
        if not (gmeta["has_transitions"] or gmeta["has_lifecycle"]):
            continue
        # expect a domain lifecycle hint somewhere
        matched = any(
            _norm(gname) == _norm(n) or _norm(gname) in _norm(n) or _norm(n) in _norm(gname)
            for n, meta in nouns.items()
            if meta["lifecycle_hint"]
        )
        if not matched:
            gold_missing_hint.append(
                {
                    "entity": gname,
                    "states": gmeta["states"],
                    "has_transitions": gmeta["has_transitions"],
                }
            )

    # Generic persona pollution (ids that appear across many apps)
    generic = {"user", "admin", "staff", "member", "owner", "customer", "provider"}
    persona_pollution = [p["id"] for p in personas if p["id"] in generic]

    return {
        "example": ex.name,
        "brief": str(brief.relative_to(REPO)),
        "n_nouns": len(nouns),
        "n_personas": len(personas),
        "nouns": nouns,
        "personas": personas,
        "persona_pollution": persona_pollution,
        "gold_status_entities": gold,
        "lifecycle_attached_to_gold": lifecycle_on_gold,
        "lifecycle_orphan_nouns": lifecycle_orphan,
        "gold_lifecycle_missing_from_domain": gold_missing_hint,
        "rejected_chrome_n": len(ad.rejected_chrome),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--example", help="Single example name")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    examples_dir = REPO / "examples"
    if args.example:
        targets = [examples_dir / args.example]
    else:
        targets = sorted(d for d in examples_dir.iterdir() if d.is_dir() and any(d.rglob("*.dsl")))

    rows = [probe(t) for t in targets if t.exists()]
    if args.json:
        print(json.dumps(rows, indent=2))
        return

    for r in rows:
        if "error" in r:
            print(f"{r['example']}: ERROR {r['error']}")
            continue
        print(f"\n=== {r['example']} ({r['brief']}) ===")
        print(
            f"  nouns={r['n_nouns']} personas={r['n_personas']} chrome_rej={r['rejected_chrome_n']}"
        )
        print(f"  persona_pollution: {r['persona_pollution'] or '—'}")
        print(f"  lifecycle→gold: {r['lifecycle_attached_to_gold'] or '—'}")
        print(f"  lifecycle orphans: {r['lifecycle_orphan_nouns'] or '—'}")
        print(
            f"  gold lifecycle missing in domain: {r['gold_lifecycle_missing_from_domain'] or '—'}"
        )
        missing = r["gold_lifecycle_missing_from_domain"]
        if missing:
            for m in missing:
                print(f"    ! {m['entity']}: {m['states']}")


if __name__ == "__main__":
    main()
