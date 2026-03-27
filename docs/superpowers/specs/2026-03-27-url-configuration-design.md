# URL Configuration — Design Spec

**Issue**: #736 — Centralize URL configuration: site_url + api_url in dazzle.toml
**Date**: 2026-03-27

## Problem

~30 locations hardcode `http://localhost:3000` (frontend) and `http://localhost:8000` (backend). Agents and deployments need to vary these per environment.

## Design

### Config Dataclass

```python
@dataclass
class URLsConfig:
    """Site and API URL configuration."""
    site_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"
```

Added to `ProjectManifest` as `urls: URLsConfig = field(default_factory=URLsConfig)`.

### TOML Section

```toml
[urls]
site_url = "http://localhost:3000"
api_url = "http://localhost:8000"
```

### Resolver Functions

Two functions in `manifest.py`, following the `resolve_database_url()` pattern:

```python
def resolve_site_url(manifest: ProjectManifest | None = None) -> str:
    """Resolve site URL. Priority: DAZZLE_SITE_URL env → toml → default."""

def resolve_api_url(manifest: ProjectManifest | None = None) -> str:
    """Resolve API URL. Priority: DAZZLE_API_URL env → toml → default."""
```

### Consumer Sweep

Every hardcoded `localhost:3000` or `localhost:8000` in `src/` gets replaced with a call to the appropriate resolver. Where a manifest is already in scope, pass it. Where it's not available, call with `None` (env var → default still works).

### Affected Files

**Critical (user-facing):**
- `src/dazzle/cli/auth.py` — magic link URL
- `src/dazzle/specs/openapi.py` — OpenAPI server URL
- `src/dazzle_back/runtime/app_factory.py` — backend URL default
- `src/dazzle_ui/runtime/page_routes.py` — backend URL
- `src/dazzle_ui/runtime/experience_routes.py` — backend URL

**Testing:**
- `src/dazzle/testing/viewport_runner.py`
- `src/dazzle/testing/e2e_runner.py`
- `src/dazzle/testing/session_manager.py`
- `src/dazzle/testing/playwright_codegen.py`
- `src/dazzle_e2e/adapters/dazzle_adapter.py`
- `src/dazzle/demo_data/loader.py`
- `src/dazzle/testing/test_runner.py`

**MCP handlers:**
- `src/dazzle/mcp/server/handlers/dsl_test.py`
- `src/dazzle/mcp/server/handlers/demo_data.py`

**CLI:**
- `src/dazzle/cli/feedback_impl.py`
- `src/dazzle/cli/quality.py`
- `src/dazzle/cli/mock.py`
- `src/dazzle/cli/project.py`

**Other:**
- `src/dazzle/testing/vendor_mock/webhooks.py`
- `src/dazzle/cli/runtime_impl/docker.py`

### Testing

- Unit tests for `URLsConfig` parsing from TOML
- Unit tests for `resolve_site_url()` and `resolve_api_url()` covering all 3 cascade levels (env var, toml, default)
- Verify existing tests still pass after the sweep

### Non-Goals

- No changes to help text or documentation strings (informational only)
- No changes to test files that construct URLs for test assertions
- No `env:VAR_NAME` indirection syntax (unlike database URLs, these are simple strings)
