# TASK-003 — retire a dead compliance helper, in the company of two live ones

**Status:** open

**From:** `tests/unit/fixtures/dead_definitions_families.json`
(`error-and-report-helpers` family), reported by `test_dead_definition_ratchet`.

## The task

`src/dazzle/compliance/analytics/consent_banner.py` defines a module-level
private helper that nothing references:

    def render_consent_banner_from_state(...)

Delete it, and retire its entries from the dead-definition ratchet and its family
list so the gate records the progress.

## What is *not* said, and is the actual task

Nothing here tells you what to read first. Finding the right record is part of
what is being measured, and so is noticing when the record itself is incomplete —
if it turns out this entry's family or retire-when condition does not describe
your case, say so in your report rather than editing the record to fit.

## The trap

Compliance helpers cluster: the module's other two helpers **are** live. If you
cannot tell which is which from the code alone, the ratchet is the authority.

## Bounds

- One function, one ratchet entry, one family entry. Nothing else.
- Do not refactor the consent module, do not reformat, do not rename survivors.
- The ratchet entries must be **removed**, not the gate loosened.
- Do not regenerate `complexity_baseline.json` unless you show it is required.

## Done when

- `uv run pytest tests/unit/test_dead_definition_ratchet.py -q` is green.
- The gate path for a `src/` diff is green (`make ci-changed` — which now also
  runs the `-m gate` suite, because this card touches a fixture).
- The commit subject states the task, and the diff is the task.

## Consuming a card

Follow the sequence at the end of `TASK-001.md`'s sibling note: record the run
first, then flip the status, then author the successor.
