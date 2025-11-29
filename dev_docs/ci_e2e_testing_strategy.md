# E2E Testing CI Strategy for DAZZLE

**Status**: Implementation Plan
**Date**: 2025-11-29
**Priority**: CRITICAL (per roadmap v0.3.1)

---

## Executive Summary

This document outlines the strategy for automated E2E testing of DAZZLE applications in CI/CD pipelines. The goal is to prevent regressions by automatically testing all example projects on every PR.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub Actions CI                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐ │
│  │ Unit Tests  │    │    Lint     │    │   Type Check        │ │
│  └──────┬──────┘    └──────┬──────┘    └─────────┬───────────┘ │
│         │                  │                      │             │
│         └──────────────────┴──────────────────────┘             │
│                            │                                    │
│                            ▼                                    │
│              ┌─────────────────────────┐                        │
│              │   E2E Matrix Tests      │                        │
│              │   (parallel execution)  │                        │
│              └─────────────────────────┘                        │
│                            │                                    │
│         ┌──────────────────┼──────────────────┐                 │
│         ▼                  ▼                  ▼                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ simple_task │    │contact_mgr  │    │ uptime_mon  │   ...   │
│  │   E2E       │    │   E2E       │    │   E2E       │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing Layers

### Layer 1: Unit Tests (Fast, No Server)
- **Location**: `tests/unit/`
- **Scope**: IR types, parser, validation, JS generation
- **Duration**: ~30 seconds
- **Dependencies**: None (pure Python)

### Layer 2: Integration Tests (No Browser)
- **Location**: `tests/integration/`
- **Scope**: DNR server startup, API endpoints, HTML generation
- **Duration**: ~2 minutes
- **Dependencies**: httpx, uvicorn

### Layer 3: E2E Tests (Full Browser)
- **Location**: Generated per-project, run via `dazzle test run`
- **Scope**: Full user flows via Playwright
- **Duration**: ~5 minutes per project
- **Dependencies**: Playwright, Chromium

---

## Example Project Test Matrix

| Example | Archetype | Priority | Expected Flows |
|---------|-----------|----------|----------------|
| `simple_task` | SCANNER_TABLE | P0 | CRUD basic |
| `contact_manager` | DUAL_PANE_FLOW | P0 | CRUD + relations |
| `uptime_monitor` | FOCUS_METRIC | P1 | View + metrics |
| `email_client` | MONITOR_WALL | P2 | Multi-signal dashboard |
| `inventory_scanner` | SCANNER_TABLE | P1 | Bulk operations |
| `ops_dashboard` | COMMAND_CENTER | P2 | Operations view |
| `archetype_showcase` | All | P1 | All archetypes |

**Priority Levels**:
- P0: Block PRs on failure (must pass)
- P1: Warn on failure (should pass)
- P2: Informational (nice to have)

---

## CI Workflow Design

### Job Dependencies

```yaml
jobs:
  unit-tests:     # Fast gate, runs first
  lint:           # Fast gate, runs first
  type-check:     # Fast gate, runs first

  integration:    # Requires unit-tests + lint
    needs: [unit-tests, lint]

  e2e-matrix:     # Parallel E2E tests per example
    needs: [unit-tests, lint]
    strategy:
      matrix:
        example: [simple_task, contact_manager, uptime_monitor, ...]
```

### E2E Job Structure

Each E2E job follows this pattern:

1. **Setup Environment**
   ```bash
   pip install -e ".[dev]"
   pip install playwright httpx
   playwright install chromium --with-deps
   ```

2. **Validate Project**
   ```bash
   cd examples/$EXAMPLE
   dazzle validate
   ```

3. **Generate Test Spec**
   ```bash
   dazzle test generate -o testspec.json
   ```

4. **Start DNR Server**
   ```bash
   dazzle dnr serve --test-mode &
   sleep 5
   curl -f http://localhost:8000/health
   ```

5. **Run E2E Tests**
   ```bash
   dazzle test run --priority high --verbose
   ```

6. **Cleanup**
   ```bash
   pkill -f "dazzle dnr serve" || true
   ```

---

## Direct DNR Testing (No Docker)

For most CI scenarios, Docker is **not required**. The DNR server runs directly:

```bash
# Start the server (background)
dazzle dnr serve --test-mode --port 8000 &

# Wait for ready
until curl -s http://localhost:8000/health > /dev/null; do
  sleep 1
done

# Run tests
dazzle test run --verbose

# Cleanup
pkill -f "dazzle dnr serve"
```

### Benefits of Direct Testing

1. **Faster startup** - No container overhead
2. **Simpler CI** - No Docker setup required
3. **Better debugging** - Direct process access
4. **Portable** - Works in any Python environment

---

## Docker Strategy (Optional)

Docker is useful for:
- Production deployment testing
- Multi-service integration (e.g., PostgreSQL)
- Consistent environment across developers

### Docker Compose for Testing

```yaml
# docker-compose.test.yml
version: '3.8'

services:
  dnr-app:
    build:
      context: .
      dockerfile: Dockerfile.test
    ports:
      - "8000:8000"
      - "3000:3000"
    environment:
      - DNR_TEST_MODE=1
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 5s
      timeout: 3s
      retries: 10

  test-runner:
    build:
      context: .
      dockerfile: Dockerfile.playwright
    depends_on:
      dnr-app:
        condition: service_healthy
    volumes:
      - ./test-results:/app/test-results
    command: ["dazzle", "test", "run", "--verbose"]
```

### When to Use Docker in CI

| Scenario | Use Docker? |
|----------|-------------|
| PR validation | No - direct testing is faster |
| Nightly regression | Yes - full environment testing |
| Release validation | Yes - production-like environment |
| Multi-database testing | Yes - for PostgreSQL/MySQL |

---

## Failure Handling

### Priority-Based Blocking

```yaml
- name: Run E2E tests (P0 - blocking)
  run: dazzle test run --priority high
  # No continue-on-error - blocks PR

- name: Run E2E tests (P1 - warning)
  run: dazzle test run --priority medium
  continue-on-error: true

- name: Run E2E tests (P2 - informational)
  run: dazzle test run --priority low
  continue-on-error: true
```

### Test Artifacts on Failure

```yaml
- name: Upload test artifacts
  if: failure()
  uses: actions/upload-artifact@v4
  with:
    name: e2e-failures-${{ matrix.example }}
    path: |
      examples/${{ matrix.example }}/test-results/
      examples/${{ matrix.example }}/testspec.json
    retention-days: 7
```

---

## Implementation Steps

### Phase 1: Update CI Workflow
1. Add E2E matrix job for P0 examples
2. Configure proper timeouts
3. Add artifact uploads for failures

### Phase 2: Example Project Readiness
1. Ensure all examples have valid DSL
2. Run `dazzle test generate` for each
3. Verify tests pass locally

### Phase 3: Monitoring
1. Track test duration trends
2. Identify flaky tests
3. Optimize slow tests

---

## Test Flakiness Prevention

### Timeouts
```yaml
- name: Run E2E tests
  run: dazzle test run --timeout 60000  # 60s per test
  timeout-minutes: 10  # Total job timeout
```

### Retry Logic
```yaml
- name: Run E2E tests with retry
  uses: nick-fields/retry@v2
  with:
    timeout_minutes: 10
    max_attempts: 2
    command: |
      cd examples/${{ matrix.example }}
      dazzle test run --priority high
```

### Stable Selectors
The semantic DOM contract (`data-dazzle-*` attributes) ensures selectors are stable across UI changes.

---

## Metrics & Reporting

### Test Report Generation

```yaml
- name: Generate test report
  if: always()
  run: |
    dazzle test report --format junit -o results.xml

- name: Publish Test Report
  uses: mikepenz/action-junit-report@v4
  if: always()
  with:
    report_paths: 'examples/*/results.xml'
```

### Coverage Dashboard

Track metrics over time:
- Test pass rate per example
- Test duration trends
- Flaky test frequency

---

## Security Considerations

### Test Mode Isolation
- `--test-mode` enables `/__test__/*` endpoints
- Only available in non-production builds
- Data is reset between test runs

### Secrets Handling
- No secrets required for E2E tests
- Tests use mock data, not production APIs

---

## Appendix: Complete Workflow

See `.github/workflows/ci.yml` for the complete implementation.

### Quick Reference Commands

```bash
# Local E2E testing
cd examples/simple_task
dazzle test generate
dazzle dnr serve --test-mode &
dazzle test run --verbose
pkill -f "dazzle dnr serve"

# CI testing (automated)
# Triggered on push/PR via GitHub Actions
```

---

**Document Owner**: Claude + James
**Last Updated**: 2025-11-29
