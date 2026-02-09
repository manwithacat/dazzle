# E2E Tests (Local Only)

These tests require a running Dazzle server and Playwright browser automation.
They are **not run in CI** — use them for local development and manual verification.

## Contents

- `test_playwright_smoke.py` — Playwright browser tests (page load, JS errors, screenshots)
- `test_fieldtest_hub_screenshots.py` — Screenshot generation for the fieldtest_hub example

## Running Locally

```bash
# Install Playwright
pip install playwright && playwright install chromium

# Start a server
cd examples/simple_task && dazzle serve --local &

# Run tests
pytest tests/e2e/ -v -m e2e
```

## CI E2E Testing

CI E2E tests live in `tests/integration/test_runtime_e2e.py` and use pure HTTP
(no browser). See `.github/workflows/ci.yml` for the `e2e-runtime` job.
