"""Post-5.8 Goal B media — contact_manager directory headshot shelf (cycle 1882)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/contact_manager/dsl/app.dsl"
CONTACT_SEEDS = ROOT / "examples/contact_manager/demo_data/Contact.jsonl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_contact_entity_declares_photo_url() -> None:
    text = APP.read_text()
    assert 'entity Contact "Contact"' in text
    assert "photo_url: url" in text


def test_home_media_shelf_first() -> None:
    """Goal B media: favourite headshots win the Home fold before metrics/queues."""
    block = _workspace_block("home")
    assert "media_shelf:" in block
    assert "source: Contact" in block
    assert "display: grid" in block
    assert block.index("media_shelf:") < block.index("directory_stats:")
    assert block.index("media_shelf:") < block.index("favourite_contacts:")
    assert (
        "focus: media_shelf, directory_stats, engagement_docs, favourite_contacts, "
        "composition, live_conversation, practice_context" in block
    )


def test_contacts_media_shelf_first() -> None:
    """Goal B media: headshot grid declared before A–Z dual-pane on Contacts."""
    block = _workspace_block("contacts")
    assert "media_shelf:" in block
    assert "source: Contact" in block
    assert "display: grid" in block
    assert block.index("media_shelf:") < block.index("favourites_queue:")
    assert block.index("media_shelf:") < block.index("contact_list:")
    assert "focus: media_shelf, favourites_queue, contact_list, contact_detail" in block


def test_contact_seeds_have_https_photo_urls() -> None:
    rows = [json.loads(line) for line in CONTACT_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 20
    with_photo = [r for r in rows if r.get("photo_url")]
    assert len(with_photo) >= 20, "Goal B media expects headshots across the directory"
    for r in with_photo:
        url = str(r["photo_url"])
        assert url.startswith("https://"), url
        assert "placehold.co" in url


def test_contact_repr_fields_are_identity_chips_not_schema_dump() -> None:
    """Cycle 1931: Home/Contacts cards must not dump Photo Url/Email/Is Favorite."""
    text = APP.read_text()
    start = text.index('entity Contact "Contact"')
    block = text[start : text.index("entity ContactNote")]
    line = block.split("repr_fields:")[1].split("\n")[0]
    assert "first_name" in line and "last_name" in line
    assert "company" in line and "phone" in line
    assert "photo_url" not in line
    assert "email" not in line
    assert "is_favorite" not in line
