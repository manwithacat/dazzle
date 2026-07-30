#!/usr/bin/env python3
"""Domain cognition residual bar for /improve (agent-first).

Measures whether AGENT_DOMAIN + gold DSL keep up with lifecycle/process priors
from ``dazzle.domain_brief.lifecycles`` (P0–P2). Residual > 0 means the loop
should re-extract domain and/or densify DSL from process_candidates /
lifecycle_hint — not WI densify.

```bash
.venv/bin/python scripts/domain_cognition_bar.py --status
.venv/bin/python scripts/domain_cognition_bar.py --next
.venv/bin/python scripts/domain_cognition_bar.py --json
.venv/bin/python scripts/domain_cognition_bar.py --reextract   # fleet save_domain
```
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"
sys.path.insert(0, str(REPO / "src"))

SHOWCASE = [
    "simple_task",
    "contact_manager",
    "support_tickets",
    "ops_dashboard",
    "fieldtest_hub",
    "invoice_ops",
    "project_tracker",
    "design_studio",
    "hr_records",
    "acme_billing",
    "llm_ticket_classifier",
    "domain_join_co",
]


@dataclass
class AppDomainScore:
    app: str
    n_nouns: int = 0
    n_with_lifecycle: int = 0
    n_process_candidates: int = 0
    n_personas: int = 0
    multi_persona_no_process: bool = False
    status_without_transitions: list[str] = field(default_factory=list)
    gold_lifecycle_missing: list[str] = field(default_factory=list)
    domain_stale: bool = False  # committed AGENT_DOMAIN lags extract
    residual: int = 0
    next_action: str = ""

    @property
    def is_residual(self) -> bool:
        return self.residual > 0


def _dsl_status_gaps(ex: Path) -> tuple[list[str], int, int]:
    text = ""
    for p in ex.rglob("*.dsl"):
        if "build" in p.parts:
            continue
        text += "\n" + p.read_text(errors="replace")
    personas = set(re.findall(r"^persona\s+(\w+)", text, re.M))
    processes = set(re.findall(r"^process\s+(\w+)", text, re.M))
    status_no: list[str] = []
    matches = list(re.finditer(r"^entity\s+(\w+)\b", text, re.M))
    for i, m in enumerate(matches):
        name = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        if not re.search(r"status:\s*enum\[", body):
            continue
        has_t = bool(re.search(r"^\s*transitions:", body, re.M))
        has_l = bool(re.search(r"^\s*lifecycle:", body, re.M))
        if not (has_t or has_l):
            status_no.append(name)
    mpp = len(personas) >= 3 and len(processes) == 0
    return status_no, len(personas), 1 if mpp else 0


def score_app(app: str, *, live_extract: bool = True) -> AppDomainScore:
    from dazzle.domain_brief.extract import extract_from_path, find_founder_brief
    from dazzle.domain_brief.store import load_domain

    ex = EXAMPLES / app
    row = AppDomainScore(app=app)
    if not ex.is_dir():
        return row

    status_no, n_pers, mpp = _dsl_status_gaps(ex)
    row.status_without_transitions = status_no
    row.multi_persona_no_process = bool(mpp)
    row.n_personas = n_pers

    brief = find_founder_brief(ex)
    if brief is None:
        for c in ("SPECIFICATION.md", "SPEC.md"):
            if (ex / c).exists():
                brief = ex / c
                break
    if brief is None or not live_extract:
        committed = load_domain(ex)
        if committed:
            row.n_nouns = len(committed.nouns)
            row.n_with_lifecycle = sum(1 for n in committed.nouns if n.lifecycle_hint)
            row.n_process_candidates = len(committed.process_candidates)
        row.residual = _residual(row)
        row.next_action = _next(row)
        return row

    ad = extract_from_path(brief)
    row.n_nouns = len(ad.nouns)
    row.n_with_lifecycle = sum(1 for n in ad.nouns if n.lifecycle_hint)
    row.n_process_candidates = len(ad.process_candidates)

    committed = load_domain(ex)
    if committed is not None:
        # Stale when extract has lifecycle/process signal that committed twin lacks
        c_life = sum(1 for n in committed.nouns if n.lifecycle_hint)
        c_proc = len(committed.process_candidates)
        if row.n_with_lifecycle > c_life or row.n_process_candidates > c_proc:
            row.domain_stale = True
        if not getattr(committed, "process_candidates", None) and row.n_process_candidates:
            row.domain_stale = True

    # Gold lifecycle missing: extract lifecycle entity not reflected when gold
    # has transitions — reverse gap is densify opportunity on DSL.
    # Here residual prefers: stale domain, multi-persona no process WITH candidates,
    # status∄trans when lifecycle_hint exists for that stem.
    row.residual = _residual(row)
    row.next_action = _next(row)
    return row


def _residual(row: AppDomainScore) -> int:
    r = 0
    if row.domain_stale:
        r += 2
    if row.multi_persona_no_process and row.n_process_candidates > 0:
        r += 2
    if row.status_without_transitions and row.n_with_lifecycle > 0:
        r += 1
    if row.n_nouns and row.n_with_lifecycle == 0 and row.n_personas >= 2:
        # thin lifecycle prior on multi-persona app
        r += 1
    return r


def _next(row: AppDomainScore) -> str:
    if row.domain_stale:
        return f"reextract:{row.app}"
    if row.multi_persona_no_process and row.n_process_candidates > 0:
        return f"process_densify:{row.app}"
    if row.status_without_transitions:
        return f"transitions:{row.app}:{','.join(row.status_without_transitions[:3])}"
    if row.n_nouns and row.n_with_lifecycle == 0:
        return f"lifecycle_prior:{row.app}"
    return ""


def scan(*, live_extract: bool = True) -> list[AppDomainScore]:
    apps = [a for a in SHOWCASE if (EXAMPLES / a).is_dir()]
    return [score_app(a, live_extract=live_extract) for a in apps]


def format_status(rows: list[AppDomainScore]) -> str:
    residual = [r for r in rows if r.is_residual]
    nxt = residual[0].app if residual else "-"
    stale = sum(1 for r in rows if r.domain_stale)
    mpp = sum(1 for r in rows if r.multi_persona_no_process)
    life = sum(r.n_with_lifecycle for r in rows)
    proc = sum(r.n_process_candidates for r in rows)
    return (
        f"domain_cognition apps={len(rows)} residual={len(residual)} "
        f"stale_domain={stale} multi_persona_no_proc={mpp} "
        f"lifecycle_hints={life} process_candidates={proc} next={nxt}"
    )


def reextract_fleet(apps: list[str] | None = None) -> dict[str, str]:
    from dazzle.domain_brief.extract import extract_from_path, find_founder_brief
    from dazzle.domain_brief.store import save_domain

    out: dict[str, str] = {}
    targets = apps or [a for a in SHOWCASE if (EXAMPLES / a).is_dir()]
    for app in targets:
        ex = EXAMPLES / app
        brief = find_founder_brief(ex)
        if brief is None:
            for c in ("SPECIFICATION.md", "SPEC.md"):
                if (ex / c).exists():
                    brief = ex / c
                    break
        if brief is None:
            out[app] = "skip:no_brief"
            continue
        ad = extract_from_path(brief)
        paths = save_domain(ex, ad)
        out[app] = (
            f"nouns={len(ad.nouns)} life={sum(1 for n in ad.nouns if n.lifecycle_hint)} "
            f"proc={len(ad.process_candidates)} → {paths['json']}"
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--reextract", action="store_true")
    ap.add_argument("--committed-only", action="store_true", help="Skip live extract")
    args = ap.parse_args()

    if args.reextract:
        result = reextract_fleet()
        print(json.dumps(result, indent=2))
        return

    rows = scan(live_extract=not args.committed_only)
    if args.json:
        print(json.dumps([asdict(r) for r in rows], indent=2))
        return
    print(format_status(rows))
    if args.next:
        residual = [r for r in rows if r.is_residual]
        if residual:
            print(f"next_action={residual[0].next_action}")
        else:
            print("next_action=-")
    for r in rows:
        if r.is_residual:
            print(
                f"  {r.app}: residual={r.residual} stale={r.domain_stale} "
                f"life={r.n_with_lifecycle} proc={r.n_process_candidates} "
                f"mpp={r.multi_persona_no_process} "
                f"status∄t={r.status_without_transitions or '—'} "
                f"→ {r.next_action}"
            )


if __name__ == "__main__":
    main()
