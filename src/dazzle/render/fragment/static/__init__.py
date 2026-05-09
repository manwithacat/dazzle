"""Static HTML+JS assets emitted verbatim by typed-Fragment chrome
primitives (WorkspaceDrawer, WorkspaceContextSelector). Loaded via
`importlib.resources.files()` at module-import time by
`renderer._load_static`.

This `__init__.py` makes the directory a proper Python package so it
gets included in the built wheel — without it, `importlib.resources`
raises `ModuleNotFoundError` on packaged installs (#1032). The
`package-data` entry in `pyproject.toml` then ships the .html files."""
