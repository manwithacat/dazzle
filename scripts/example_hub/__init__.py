"""Local multi-host evaluation hub for Dazzle example apps.

See docs/superpowers/specs/2026-07-21-example-eval-hub-design.md
"""

from __future__ import annotations

__all__ = ["HUB_DOMAIN", "DEFAULT_HUB_PORT", "DEFAULT_BACKEND_BASE"]

HUB_DOMAIN = "dazzle.local"
DEFAULT_HUB_PORT = 9080
DEFAULT_BACKEND_BASE = 9100
