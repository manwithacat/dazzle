"""Download filenames must not dump EngagementLetter (oral #195)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_csv import render_entity_list_csv
from dazzle.render.breadcrumbs import (
    clerk_entity_download_stem,
    entity_path_labels_from_spec,
)

SUPPORT = Path("examples/support_tickets")


def test_support_sla_waiver_download_stem_is_live() -> None:
    spec = load_project(SUPPORT)
    waiver = next(e for e in spec.domain.entities if e.name == "SlaWaiver")
    assert waiver.title == "SLA Waiver"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_download_stem("SlaWaiver", labels) == "sla-waiver"


def test_entity_list_csv_filename_engagement_letter_not_pascal() -> None:
    columns = [{"key": "title", "label": "Title", "type": "text"}]
    resp = render_entity_list_csv([{"title": "Q3 retainer"}], columns, "EngagementLetter")
    cd = resp.headers["content-disposition"]
    assert 'filename="engagement-letter.csv"' in cd
    assert "EngagementLetter.csv" not in cd
