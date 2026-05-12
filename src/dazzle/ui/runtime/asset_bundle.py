"""Asset bundling resolver.

Resolves the project's `[ui] assets` setting + environment + CLI overrides
into a single boolean `_bundle_assets` that `base.html` branches on.

Three configured modes:
  - "auto"   = bundle when DAZZLE_ENV=production, individual scripts in dev
  - "always" = bundle in every environment (perf testing / staging)
  - "never"  = individual scripts always (advanced live-reload during prod debugging)

CLI overrides:
  - `dazzle serve --bundle`     forces bundled mode regardless of manifest
  - `dazzle serve --no-bundle`  forces individual mode regardless of manifest

Heroku-friendly: the framework's `dist/dazzle.min.js` ships in the
dazzle-dsl wheel. When `pip install dazzle-dsl` runs on Heroku slug
build, the bundle lands in `site-packages/dazzle_ui/runtime/static/dist/`
and is served alongside the unbundled scripts. No build step at runtime;
everything is precomputed at framework release time.
"""

from __future__ import annotations

import os
from typing import Literal

AssetsMode = Literal["auto", "always", "never"]
CliOverride = Literal["bundle", "no-bundle"] | None


def should_bundle_assets(
    mode: AssetsMode = "auto",
    *,
    env: str | None = None,
    cli_override: CliOverride = None,
) -> bool:
    """Resolve `[ui] assets` mode + environment + CLI override into a boolean.

    Args:
        mode: Manifest setting from `dazzle.toml`'s `[ui] assets`. Defaults
            to ``"auto"`` so projects without the field work as before.
        env: Environment name. Defaults to reading `DAZZLE_ENV` from the
            process environment. Recognised values:
            ``"production"`` / ``"staging"`` → bundle if mode is "auto".
            Anything else (including missing) → individual scripts.
        cli_override: ``"bundle"`` or ``"no-bundle"`` from CLI flags.
            Highest priority — if set, manifest mode is ignored.

    Returns:
        True if the rendered template should load the framework dist
        bundle (`dist/dazzle.min.{js,css}`); False if it should load the
        individual scripts and the source `dazzle.css`.
    """
    if cli_override == "bundle":
        return True
    if cli_override == "no-bundle":
        return False

    if mode == "always":
        return True
    if mode == "never":
        return False

    # mode == "auto": environment-driven
    resolved_env = env if env is not None else os.environ.get("DAZZLE_ENV", "")
    return resolved_env.lower() in ("production", "staging")
