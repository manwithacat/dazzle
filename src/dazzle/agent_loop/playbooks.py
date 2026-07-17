"""Agent playbook bodies (#1605 / #1617) — kept out of core.py for MI."""

from __future__ import annotations

from typing import Any

PLAYBOOK_DOMAIN_LOGIC = """# Playbook: domain_logic closed loop (#1605)

## Thesis
Structure tools are not enough. Domain behaviour lives in services/routes/process.
Agents must **map → bind → scaffold → prove --static**, not dual-lock chrome.

## ADR-0002
- **MCP** — `agent(operation=context|prove|playbook)` when mcp extra installed
- **CLI (default dual-lock path)** — no mcp required:
  - `dazzle agent context`
  - `dazzle prove story --static`
  - `dazzle agent playbook domain_logic`
  - `dazzle scaffold …`
  - `dazzle story bind-migrate …`

## Loop
1. **Map** — `dazzle agent context`
2. **Bind** — `executed_by:` or `narrative_only: true` on every accepted story
3. **Scaffold** — `dazzle scaffold service|story|process-step …`
4. **Prove** — `dazzle prove story --static` (binding evidence only)
5. **Gate** — validate fails accepted+unbound

## Language
- `pass_static` / `fail_static` — binding target exists in DSL/host map
- `pass_runtime` / `fail_runtime` / `skip_runtime` — host module readiness
  (service file, entrypoint, not scaffold-only). **Not** browser e2e.
- `pass_journey` / `fail_journey` / `skip_journey` — surface hub / open-via
  hop graph + process host ready. **Still not** Playwright e2e.
- `dazzle prove story --runtime` / `--journey`

## Story wall (binding)
- `dazzle agent wall` — buckets: pass_journey / fail_journey / pass_static /
  fail_static / narrative_only / unbound_accepted
- MCP `story(operation=get, view=wall)` includes the same binding buckets
- `agent context` → `story_wall` for session start

## Data shape (related)
For multi-parent / attachable / custom-field domains use playbook
`domain_data_shape` (#1617) before dual-locking open-via or inventing poly keys.
"""

PLAYBOOK_DOMAIN_DATA_SHAPE = """# Playbook: domain_data_shape (#1617)

## Thesis
Default is purist (`rel.explicit_ref`). Escape hatches are **named product
features**, not host folklore. Agents must **decide → author → classify → prove**.

## Pattern IDs (use these words)
| ID | When |
|----|------|
| `rel.explicit_ref` | Single parent `ref` |
| `rel.exclusive_fks` | 2–4 alternative parents + `first_non_null` |
| `rel.poly_ref` | Shared child → many parents (after four questions) |
| `rel.tpt_subtype` | True ISA + mixed list (`subtype_of:`) |
| `rel.json_extension` | Core columns + `json` bag |
| `rel.host_extension` | Dual-lock host schema only |

**Exclusive FKs ≠ poly_ref.** Company|sole_trader clients are exclusive FKs.

## Loop
1. **Decide** — `dazzle representation decide --text '…'` or MCP
   `representation(operation=decide, text=…)`
2. **Author** — DSL sketch from decide (invariant + open for exclusive FKs)
3. **Classify** — `dazzle representation classify -p .`
4. **Prove** — `dazzle prove representation -p .`
5. **DB verify** (optional) — `dazzle db verify` for `exclusive_conflict` rows

## Commands
```bash
dazzle representation patterns
dazzle representation decide --text "company or sole trader client"
dazzle representation classify -p .
dazzle prove representation -p .
dazzle agent wall -p . --markdown   # includes Representation: OK|FAIL line
dazzle agent playbook domain_data_shape
```

## Bootstrap
Mission briefing `analysis.representation_decision` already ran decide on the
spec — honour that `pattern_id` when generating entities.
"""


def build_playbook(name: str = "domain_logic") -> dict[str, Any]:
    n = (name or "domain_logic").strip()
    if n in ("domain_logic", "domain-logic", "default"):
        return {
            "ok": True,
            "operation": "playbook",
            "name": "domain_logic",
            "body": PLAYBOOK_DOMAIN_LOGIC,
        }
    if n in ("domain_data_shape", "domain-data-shape", "data_shape", "representation"):
        return {
            "ok": True,
            "operation": "playbook",
            "name": "domain_data_shape",
            "body": PLAYBOOK_DOMAIN_DATA_SHAPE,
        }
    return {
        "ok": False,
        "error": f"Unknown playbook: {n}. Known: domain_logic, domain_data_shape",
    }
