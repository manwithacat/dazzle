# TASK-002 — retire a dead CLI helper without touching its live neighbour

**Status:** open

**From:** `tests/unit/fixtures/dead_definitions_families.json`
(`cli-parity-helpers` family), reported by `test_dead_definition_ratchet`.

## The task

`src/dazzle/cli/runtime_impl/ports.py` defines a module-level private helper
that nothing references:

    def read_runtime_file(...)

Delete it, and retire its entry from the dead-definition ratchet so the gate
records the progress.

## What is *not* said, and is the actual task

Nothing here tells you what to read first. Finding the right record is part of
what is being measured. Two bear on this change:

- `docs/reference/dead-code-residue.md` — the family this entry belongs to, and
  what retires the family. Read it *after* deciding where the helper is used,
  not before: naming the residue in prose is bookkeeping, not a use site, and the
  ratchet is explicit about that now.
- `docs/harness/principle-gates.md` — which gate defends the rule you are about
  to touch.

## The trap

The same module keeps `load_runtime_file`-style neighbours that **are** live. If
you cannot tell which is which from the code alone, the ratchet is the
authority — not your reading of the directory.

## Bounds

- One function, one baseline entry, one families entry. Nothing else.
- Do not refactor the ports module, do not reformat, do not rename the survivors.
- The ratchet entries must be **removed**, not the gate loosened.

## Done when

- `uv run pytest tests/unit/test_dead_definition_ratchet.py -q` is green.
- The gate path for a `src/` diff is green (`make ci-changed`).
- The commit subject states the task, and the diff is the task.

## How the run is scored

By an observer reading the commit, the gate state and the run report. The five
assertions are in `docs/harness/orientation-benchmark.md`.
