# The harness's tool floor

What this harness assumes a host provides, what it does without, and where the
line between "degrade and note it" and "do not proceed" sits. Written for an
agent that has never seen this repo — and for the person deciding whether an
alternate agent can be swapped in.

The machine-readable form is `tests/unit/fixtures/toolchain_capabilities.json`;
the probe is `scripts/improve_toolchain.py`. This page explains them.

```bash
uv run python scripts/improve_toolchain.py --status          # what this host has
uv run python scripts/improve_toolchain.py --require playwright   # gate, exits 1 if missing
uv run python scripts/improve_toolchain.py --json            # machine-readable
```

## The floor

| Capability | Needed for | Without it |
|---|---|---|
| `uv` | everything — the repo is uv-managed (`python-preference = only-managed`) | nothing works; `make dev-install` is the setup |
| `git` | ship discipline, gates that diff against `origin/main` | stop: the gates cannot attest anything |
| `gh`, authenticated | issue triage, CI badge snapshot, PR merge, push-gate | the work may proceed, but **log `github: unavailable`** — never invent a green badge |
| `make` | the tier vocabulary (`ci-fast`, `ci-changed`, `preflight-surface`, `push-gate`) | substitute the underlying command; note the degradation |
| `postgres` | any runtime path: serve, migrate, integration tests, live walks | DSL/IR work is unaffected; every live-path task is `BLOCKED` |
| `playwright` **and** its browser binary | `qa smoke-crawl`/`smoke-dig`, journey/story walks, visual probes | those tasks are `BLOCKED` — never a stamped PASS. The package alone is not enough: `playwright install chromium` is a separate download and the step that gets missed |
| a **served app** (`served-app`) | every live walk (smoke, journey, acceptance panel, story walk) | same — `BLOCKED` with the remedy |

## Capability mapping: features vs binaries

`AGENTS.md`'s Capability Mapping table maps harness **features** (ask-user-choice,
task-list, subagent-dispatch, scheduled-loop, …) across named hosts. Features are
what the *harness* asks the host to do; **binaries** are what the harness *runs*.
This page is the binary floor. A host can satisfy every row of that table and
still be unable to do the work — for instance a CLI with no `gh` authentication
can hold a perfectly good task list and cannot read the issue inbox.

## For a host that lacks part of the floor

1. Run the probe and record what is missing.
2. Prefer work whose capabilities you have: DSL/IR work, gate authoring, docs —
   none need a browser.
3. When a task needs something absent, report `BLOCKED` **with the remedy**.
4. Do not substitute a different tool silently. A substitute is a different claim.
