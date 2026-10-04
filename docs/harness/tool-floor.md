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
| `gh`, authenticated | inbox (Step 0c3), CodeQL (0c2), CI badge (0c), PR merge, push-gate | the cycle may run, but **log `github: unavailable` and continue** — never invent a green badge |
| `make` | the tier vocabulary (`ci-fast`, `ci-changed`, `preflight-surface`, `push-gate`) | substitute the underlying command; note the degradation |
| `postgres` | any runtime path: serve, migrate, integration tests, live walks | DSL/IR work is unaffected; every live-path dig is `BLOCKED` |
| `playwright` **and** its browser binary | `qa smoke-crawl`/`smoke-dig`, demo fleet, journey/story walks, visual probes, UX walks | those strategies are `BLOCKED` — never a stamped PASS. The package alone is not enough: `playwright install chromium` is a separate download and the step that gets missed |
| a **served app** (`served-app`) | every live dig (smoke, journey, acceptance panel, story walk) | same — `BLOCKED` with the remedy, or fall back to a capability-free dig |
| `scheduler_create` | **the loop's own continuity** (Step 6b) | cycles run, but the chain does not. `--chain-armed 0` records it and `make reconcile` reports it |

## The rule the loop now follows

Step 0b runs the probe **before** lane selection, and a strategy whose
capabilities are missing is not selected into a dead end. The playbooks carry
the matching `BLOCKED` row. `tests/unit/test_toolchain_probe.py` fails if a
playbook reaches for a tool without declaring it — so this page and the fixture
cannot fall behind the playbooks.

Nine playbooks were found reaching for undeclared tools when this was built
(`api_surface_audit`, `distill`, `dual_lock_expand`, `explore-subagent`,
`semgrep_hygiene`, `hyperpart_presentation`, `trial_signal_action`,
`visual_tier2_subagent`, `domain_lifecycle_priors`). That is the shape the gate
is for: a dependency nobody wrote down.

## Why `scheduler_create` is called out

It is the only capability whose absence is invisible. Every other missing tool
produces an error at the moment it is used. This one produces **silence**: the
cycle completes, logs a scheduling decision, and no further cycle ever runs —
which is indistinguishable from a loop with nothing to do. It is how this loop
sat parked for 30 days while its courtesy work (inbox, CodeQL, compaction,
capability sweep) silently stopped with it.

The mitigation is not a fallback scheduler — it is making the state legible:

```bash
make reconcile      # reports: improve-chain … the next cycle will not run
```

An operator or an agent that finds `improve-chain` in the output knows to arm a
scheduler (a CI cron, a local `while` loop, a human) or to run cycles by hand.

## Capability mapping: features vs binaries

`AGENTS.md`'s Capability Mapping table maps harness **features** (ask-user-choice,
task-list, subagent-dispatch, scheduled-loop, …) across named hosts. Features are
what the *harness* asks the host to do; **binaries** are what the harness *runs*.
This page is the binary floor. A host can satisfy every row of that table and
still be unable to run a cycle — for instance a Codex-style CLI with no `gh`
authentication can hold a perfectly good task list and cannot read the inbox.

## For a host that lacks part of the floor

1. Run the probe and record what is missing.
2. Prefer work whose capabilities you have: `framework-ux` DSL/IR work, gate
   authoring, docs — none need a browser.
3. When a dig needs something absent, report `BLOCKED` **with the remedy**. That
   is a first-class outcome (Step 2's union includes it) and it costs one cycle.
4. Do not substitute a different tool silently and do not stamp the capability
   `USED`. A stamp is a claim; a substitute is a different claim.
