"""
Ejection adapters for generating standalone code.

Each adapter generates code for a specific target:
- Backend adapters: FastAPI, Django, Flask
- Frontend adapters: React, Vue, Next.js
- Testing adapters: Schemathesis, Playwright
- CI adapters: GitHub Actions, GitLab CI
"""

from .base import (
    AdapterRegistry,
    BackendAdapter,
    CIAdapter,
    FrontendAdapter,
    TestingAdapter,
)
from .ci import GitHubActionsAdapter
from .fastapi_impl import FastAPIAdapter
from .react import ReactAdapter
from .testing import PytestAdapter, SchemathesisAdapter

__all__ = [
    # Base classes
    "BackendAdapter",
    "FrontendAdapter",
    "TestingAdapter",
    "CIAdapter",
    "AdapterRegistry",
    # Implementations
    "FastAPIAdapter",
    "ReactAdapter",
    "SchemathesisAdapter",
    "PytestAdapter",
    "GitHubActionsAdapter",
]
