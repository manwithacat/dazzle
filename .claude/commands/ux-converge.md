Run UX contract verification in a converge-to-zero loop. Each cycle: run contracts, classify failures, fix what's fixable, re-run, confirm count drops. Stop when zero failures or stuck.

ARGUMENTS: $ARGUMENTS

## Prerequisites

- A running Dazzle server (`dazzle serve --local` from the example directory)
- PostgreSQL + Redis running
- Set `DAZZLE_SITE_URL` and `DAZZLE_API_URL` if not using runtime.json

## Loop

```
RUN CONTRACTS → CLASSIFY FAILURES → FIX → RE-RUN → COUNT DROPPED?
     ↑                                              │
     │              yes ─────────────────────────────┤
     │                                               │
     │              no (stuck) → REPORT + STOP ──────┘
     └───────────────────────────────────────────────┘
```

Run continuously until:
- **Zero failures** → update baseline, commit, done
- **Count unchanged for 2 cycles** → report remaining issues as unfixable in this session, update baseline, commit
- **All remaining failures classified as "genuine"** → file GitHub issues, update baseline, commit

## Step 1: Run Contracts

```bash
cd <example_dir>  # Must be in the example project directory
dazzle ux verify --contracts
```

Parse the output to extract: total contracts, passed, failed, pending, and each failure line.

## Step 2: Classify Each Failure

For each failed contract, fetch the actual HTML and determine the category:

| Category | Signal | Action |
|----------|--------|--------|
| **Checker calibration** | HTML has the element but checker assertion is wrong (wrong selector, wrong attribute name) | Fix `contract_checker.py` |
| **Contract generation** | Wrong persona, missing surface mode gate, incorrect permission derivation | Fix `contracts.py` |
| **CLI routing** | 403 because wrong persona authenticated, entity ID not found | Fix `ux.py` |
| **Template bug** | HTML genuinely missing the element the DSL says should be there | Fix the template in `src/dazzle_ui/` |
| **Permission model gap** | DSL says permitted but template doesn't render the action | Investigate DSL vs template, fix whichever is wrong |
| **Genuine framework issue** | Unfixable without major work | File GitHub issue, skip |

### How to classify

For each failure, run:
```python
# Fetch the actual page HTML
import httpx
resp = httpx.get(url, cookies=session_cookie)
# Search for the expected element
# If found with different attribute → checker calibration
# If not found at all → template bug or permission gap
```

Use a subagent to investigate multiple failures in parallel when there are 3+.

## Step 3: Fix

- **Checker/generation/CLI fixes**: Edit the file, run `pytest tests/unit/test_ux_*.py -x`, commit
- **Template fixes**: Edit the template, no test needed (the contract re-run IS the test)
- **Framework issues**: File a GitHub issue with `gh issue create`, note it in the cycle log

## Step 4: Re-run and Compare

```bash
dazzle ux verify --contracts
```

Compare failure count to previous cycle. If it dropped, continue. If unchanged, classify remaining as genuine and stop.

## Step 5: Finalize

When converged (or stuck):

```bash
# Update baseline with current state
dazzle ux verify --contracts --update-baseline

# Commit all fixes
git add -u
git commit -m "fix(ux): contract convergence — N fixes, M remaining"
git push
```

Report summary: starting failures, ending failures, what was fixed, what remains.

## Cycle Log

Append to `dev_docs/ux-converge-log.md` (gitignored) after each cycle:

```markdown
## Cycle N — YYYY-MM-DD HH:MM
- **Example**: fieldtest_hub
- **Starting**: 23 failed / 121 total
- **Fixed**: 5 checker calibrations, 2 contract generation
- **Ending**: 16 failed / 121 total
- **Remaining**: 13 RBAC mismatches (genuine), 3 template bugs (filed #NNN)
```

## Arguments

- No arguments: run against current directory
- `simple_task`, `fieldtest_hub`, etc.: cd to that example first
- `--max-cycles N`: limit iterations (default: 5)
