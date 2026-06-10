"""#1358: near-miss scenario keys must error, not silently drop their block.

`persona_entries:` / `personas:` / `seed_data_path:` all parsed without error
while contributing nothing to IR — support_tickets shipped three inert
scenarios for months. The tolerate-unknown path now raises actionable errors
for these specific names.
"""

from pathlib import Path

import pytest

from dazzle.core.parser import parse_modules

PREAMBLE = 'module deadkeys\n\napp deadkeys "Dead Keys"\n\n'


def _parse(tmp_path: Path, body: str):
    f = tmp_path / "app.dsl"
    f.write_text(PREAMBLE + body, encoding="utf-8")
    return parse_modules([f])


@pytest.mark.parametrize(
    ("key", "hint_fragment"),
    [
        ("persona_entries", "as persona <name>:"),
        ("personas", "as persona <name>:"),
        ("seed_data_path", "seed_script"),
    ],
)
def test_dead_scenario_key_raises_actionable_error(
    tmp_path: Path, key: str, hint_fragment: str
) -> None:
    body = f'scenario s "S":\n  {key}:\n    customer: start_route="/x"\n'
    with pytest.raises(Exception, match=hint_fragment.replace("<", "<")) as exc_info:
        _parse(tmp_path, body)
    assert key in str(exc_info.value)


def test_as_persona_entries_populate_ir(tmp_path: Path) -> None:
    body = (
        'scenario s "S":\n'
        '  description: "d"\n'
        '  seed_script: "fixtures/data.json"\n'
        "  as persona customer:\n"
        '    start_route: "/tickets"\n'
        "  as persona agent:\n"
        '    start_route: "/queue"\n'
    )
    mods = _parse(tmp_path, body)
    (scenario,) = mods[0].fragment.scenarios
    assert [(e.persona_id, e.start_route) for e in scenario.persona_entries] == [
        ("customer", "/tickets"),
        ("agent", "/queue"),
    ]
    assert scenario.seed_data_path == "fixtures/data.json"
