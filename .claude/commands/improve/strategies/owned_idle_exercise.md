# Strategy: owned_idle_exercise (driver-level)

First-exercise (or re-exercise after long idle) an `OWNED-IDLE` capability from
`improve/capability-map.md`. Invoked by driver Step 1 rule 7 when no
UNOWNED/STALE work remains, or when an OWNED-IDLE row has never been stamped.

**Force path:** `/improve <owning-lane>` then name the capability in the log, or
pick via rule 7 automatically.

## Priority among OWNED-IDLE

1. `last-exercised = —` (never) over previously stamped
2. In-loop owners (`hm-convergence`, `framework-ux`, `example-apps`, …) before
   `(standalone)` entrypoints
3. Subscription / free paths before metered API paths

## Exercise catalog (one capability per cycle)

| Capability | How to exercise (no human) | Budget | Stamp as |
|------------|----------------------------|--------|----------|
| **`hm gallery interaction probes`** | `python scripts/hm_gallery_probes.py --run` — drain FAIL rows per `improve/strategies/gallery_probes.md`. Prefer this over static vision when dual-lock queue is gallery-only. | 1 | USED on completed run (PASS or FAIL-with-fix) |
| `dazzle qa taste-panel` | **Do not** call the metered judge by default. Prefer subscription vision: `python scripts/hm_visual_smoke.py --dazzle-emit` then `python scripts/hm_subscription_vision.py --from-smoke --write-prompt` + host-Read scores + ingest. Log that taste-panel *metered* remains optional. | 1–2 | USED if smoke+subscription path completed; else leave OWNED-IDLE with note |
| `dazzle qa component-vision` / `property-vision` | Same: subscription host-Read path over showcase PNG / property capture. Metered CLI only if `ANTHROPIC_API_KEY` has credit **and** operator forced. | 1–2 | USED on successful advisory score or subscription substitute |
| `/fuzz` | Follow `.claude/commands/fuzz.md` in-process: scout apps → static boot-stderr signatures (or workflow if available) → dedup `gh` → file HIGH/MEDIUM only. Side-effect (issues) is allowed. | 1 | USED@N on owning standalone (or framework-ux if stamped under improve) |
| `/smells` | Follow smells skill: regression checks + one new systemic pattern pass; **read-only** unless a trivial local fix is obvious. Prefer `dazzle fitness code` as the deterministic substrate. | 1 | USED@N |
| `/xproject` | Only if sibling repos are present and readable; otherwise log `BLOCKED — no siblings` and pick another OWNED-IDLE. Do not invent sibling paths. | 1 | USED or leave idle with BLOCKED note |

## Hard rules

- **One capability per cycle.** Don't chain OWNED-IDLE exercises.
- **Subscription over metered.** Taste/vision must not burn API credits in the
  default loop (`docs/reference/taste.md`).
- **Standalone loops may file issues** (fuzz) but must not force-push, release,
  or edit shared deploy config.
- Stamp `last-exercised = N` and flip OWNED-IDLE → USED when the exercise
  actually ran (failed-but-exercised still stamps USED with a note in the log).
