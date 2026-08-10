"""Region filter `field != null` must reach SQL (cycle 1884 media_shelf)."""

from __future__ import annotations

import logging
from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.http.runtime.scope_filters import _extract_condition_filters


def test_simple_task_media_shelf_photo_url_not_null_filter() -> None:
    spec = load_project_appspec(Path("examples/simple_task"))
    ws = next(w for w in spec.workspaces if w.name == "team_overview")
    reg = next(r for r in ws.regions if r.name == "media_shelf")
    filters: dict = {}
    _extract_condition_filters(reg.filter, "uid", filters, logging.getLogger("t"), None)
    assert filters.get("is_active") is True
    assert filters.get("photo_url__isnull") is False, filters
