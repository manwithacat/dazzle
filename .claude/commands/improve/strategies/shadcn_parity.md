# Strategy: shadcn_parity

**Lane:** hm-convergence
**Force path:** `/improve hm-convergence shadcn_parity`
**Inventory:** `python packages/hatchi-maxchi/tools/shadcn_parity.py --gaps-only`
**Map:** `packages/hatchi-maxchi/SHADCN_PARITY.md`

Close the gap between the public **shadcn/ui component catalogue** and what
HM offers UX developers. Goal: **parity at minimum** — every shadcn surface
either has a Hyperpart, is covered by a deliberate partial (forms/layout),
or is explicitly `n/a`.

This strategy **seeds and drains placeholders**. Dual-locks come after the
surface exists (`dual_lock_expand`).

## When to pick

- Queue of `gap` rows > 0 (`shadcn_parity.py --gaps-only`)
- Operator forced `shadcn_parity`
- After a shadcn catalogue bump (re-pin `SHADCN_CATALOGUE_DATE` in the tool)

Prefer **over** dual_lock_expand when gaps include high-traffic UX primitives
(switch, item, carousel, hover-card, menubar, kbd, chat message). Prefer
**under** dual_lock_expand when gaps are empty and dual-lock queue is deep.

## Preflight

```bash
python packages/hatchi-maxchi/tools/shadcn_parity.py --write
python packages/hatchi-maxchi/tools/shadcn_parity.py --gaps-only
python scripts/hm_tailwind_reservoir.py   # floors must stay green
```

## Playbook (one cycle = one gap → gallery stub + optional CSS shell)

### 1. Pick a gap

From `--gaps-only` / `SHADCN_PARITY.md` Gaps table, take the top PENDING
`HMC-NNN` with `scope = shadcn_parity <id>` (or create one if missing).

Skip / BLOCKED if:

- Job is already `partial` with a clear compose path (do not invent a twin)
- Invention ladder says refuse (`docs/agent/invent-safely.md`)

### 2. Placeholder bar (minimum shippable for the loop)

A **placeholder** is enough for the improve loop to keep chewing:

| Layer | Minimum |
|-------|---------|
| Registry | `Hyperpart(id, title, group, blurb, partial HTML, notes="PLACEHOLDER — shadcn parity", tags=…)` |
| CSS (optional) | `components/<id>.css` with root class + token-only rules, `HYPERPART:` marker if controller later |
| Agent stub | site rebuild writes `site/agents/<id>.md` |
| Contract | **Not required** for placeholder — promote later via dual_lock_expand |
| Backlog | HMC row → IN_PROGRESS → DONE with "placeholder" note |

**Do not** claim dual-lock or schema parity on a placeholder.

### 3. Design rules for placeholders

- **Hypermedia-native:** SSR HTML, no React runtime. State in DOM attrs.
- **Compose first:** if card+button+stack express it, Blueprint — not a part.
- **Name honestly:** prefer shadcn id when it matches the job (`switch`, `kbd`);
  map sheet→drawer, sonner→toast notes rather than cloning names blindly.
- **Empty partial OK** if it documents the root class + data-* seams the
  future controller will own.

### 4. Promote path (later cycles)

1. Fill real partial + CSS (still no dual-lock)
2. Controller if platform lacks a primitive
3. `contracts/<stem>.py` + dual_lock_expand
4. Dazzle emission path when product needs it
5. Flip map status gap → partial/parity (`_MAP` in `shadcn_parity.py`) + `--write`

### 5. Re-pin catalogue

When shadcn docs add "New" components, update `_MAP` + `SHADCN_CATALOGUE_DATE`
in `tools/shadcn_parity.py`, regenerate, seed new HMC rows.

### 6. Outcome

```text
status: PASS | FAIL | BLOCKED | EXPLORED
summary: shadcn_parity {id} → placeholder Hyperpart; gaps N→M
budget_consumed: 0 if shipped, 1 if survey-only
```

## Related

- Map: `packages/hatchi-maxchi/SHADCN_PARITY.md`
- Dual-lock after surface: `improve/strategies/dual_lock_expand.md`
- Authoring: `packages/hatchi-maxchi/contracts/AUTHORING.md`
- Taste: `docs/reference/taste.md` (before real styling)
