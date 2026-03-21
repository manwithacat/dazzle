Monitor CI/CD pipeline status. Checks both the current branch and the CI badge workflow on main.

## 1. Check the CI badge workflow (always)

The README badge tracks the `CI` workflow on `main`. Always check this first:

```bash
gh run list --workflow ci.yml --branch main --limit 1 --json status,conclusion,databaseId,url
```

Report whether the badge is green or red. If red, this takes priority — investigate and fix before other work.

## 2. Find runs for the current branch

```bash
gh run list --branch $(git branch --show-current) --limit 5 --json status,conclusion,name,url,databaseId,event,workflowName
```

## 3. Poll in-progress runs

For each `in_progress` or `queued` run, poll every 15 seconds up to 20 attempts:

```bash
gh run view <run-id> --json status,conclusion,name
```

Show a brief status update each poll.

## 4. Per-job breakdown

For each completed run, show individual job results:

```bash
gh run view <run-id> --json jobs --jq '.jobs[] | {name, conclusion, startedAt, completedAt}'
```

Present as a table:

| Job | Status | Duration |
|-----|--------|----------|
| Python Tests | success | 2m 15s |
| Security Tests | success | 1m 30s |
| ... | ... | ... |

The CI workflow has these jobs (all must pass for a green badge):
- `python-tests` — Unit tests with coverage (~8000 tests)
- `security-tests` — JWT, ASVS, sanitization, bandit
- `lint` — ruff + bandit + DSL validation + AsyncAPI
- `type-check` — mypy on core + backend
- `integration` — Integration tests (depends on tests + lint + security)
- `e2e-smoke` — Example project validation + serve tests
- `postgres-tests` — Full test suite against PostgreSQL
- `e2e-runtime` — CRUD + DSL tests against PostgreSQL
- `homebrew-validation` — Formula syntax + version consistency

## 5. Diagnose and fix failures

For each failed job:

1. Fetch logs: `gh run view <run-id> --log-failed | tail -100`
2. Categorize the failure:
   - **Type error** (mypy) → fix locally with `mypy src/dazzle_back/ --ignore-missing-imports`
   - **Lint failure** (ruff) → fix locally with `ruff check src/ tests/ --fix && ruff format src/ tests/`
   - **Test failure** → identify the test, run locally with `pytest <test_file> -x -v`
   - **Security failure** (bandit) → check the flagged code
   - **Flaky/infra** (timeout, network) → note as transient, suggest re-run
3. **Fix ALL errors — including pre-existing ones.** The goal is a green badge, not just validating your own changes. If the CI was already red before your push, fix those errors too. Pre-existing mypy errors, lint warnings, or test failures should be fixed in a separate commit with a message like `fix: resolve pre-existing mypy errors in <file>`.
4. Commit, push, and re-poll until the badge is green.

## 6. Report summary

```
## CI Status

**Badge (main):** ✅ green | ❌ red (failing since <date>)
**Current branch:** <branch> — <status>

### Job Results (run #<id>)
| Job | Result |
|-----|--------|
| ... | ...    |

### Action Required
- <what needs fixing, if anything>
```
