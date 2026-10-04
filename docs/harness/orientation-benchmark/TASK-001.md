# TASK-001 — delete a dead auth helper, correctly

**Status:** spent — consumed by the first run (see `dev_docs/orientation-benchmark/runs.json`).

**From:** `tests/unit/fixtures/dead_definitions_families.json`
(`superseded-runtime-path` family), reported by `test_dead_definition_ratchet`.

## The task

`src/dazzle/http/runtime/auth/scim_provisioning.py` defines a module-level
private helper that nothing references:

    def _member_ids(value: Any) -> list[str]:
        """Member ids from a SCIM ``members`` value — leftover is empty, not a crash."""
        return leftover_honest_scim_member_ids(value) or []

Delete it, and retire its entry from the dead-definition ratchet so the gate
records the progress.

## What is *not* said, and is the actual task

Nothing here tells you what to read first. Finding the right record is part of
what is being measured. Three of them bear on this change:

- `docs/reference/dead-code-residue.md` — the family this entry belongs to, and
  the condition under which the family retires.
- `docs/harness/principle-gates.md` — which gate enforces the rule you are about
  to touch, and what "failing" looks like for it.
- `AGENTS.md` → **Ship Discipline** — what must pass before a push, and which
  target that is for a diff of this shape.

The neighbouring helper `leftover_honest_scim_member_ids` in the same file is
**live** and is the reason the dead one is a plausible-looking target. Do not
touch it. If you cannot tell the difference from the code alone, that is the
finding.

## Bounds

- The change is one function and one baseline entry. Nothing else.
- Do not refactor the SCIM path, do not "fix" the docstring of the surviving
  helper, do not reformat.
- The ratchet entry must be removed rather than the gate loosened.

## Done when

- `uv run pytest tests/unit/test_dead_definition_ratchet.py -q` is green.
- `make ci-changed` (or the equivalent gate path for a `src/` diff) is green.
- The commit subject states the task, and the diff is the task.

## How the run is scored

By an observer reading the commit, the gate state and the run report — not by
the agent's own assessment. The five assertions are in
`docs/harness/orientation-benchmark.md`.
