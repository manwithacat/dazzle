"""support_tickets adopts widget=switch on settings-like booleans (cycle 1780)."""

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.qa.hyperpart_opportunity import scan_appspec

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples" / "support_tickets"


def test_dsl_declares_switch_on_settings_bools() -> None:
    text = (APP / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "field is_active" in text and "widget=switch" in text
    assert "field is_internal" in text
    assert text.count("widget=switch") >= 3


def test_switch_opportunities_emit_covered() -> None:
    appspec = load_project_appspec(APP)
    opps = scan_appspec(appspec)
    switches = [o for o in opps if o.hyperpart == "switch"]
    assert switches
    assert all(o.status == "emit_covered" for o in switches), [
        (o.surface, o.field, o.status) for o in switches
    ]
