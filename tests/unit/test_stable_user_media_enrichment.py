"""STABLE User media enrichment after auth mirror (Goal B photo_url)."""

from __future__ import annotations

from dazzle.demo_data.test_mode_load import _stable_user_media_enrichment
from dazzle.product_quality.persona_homes import STABLE_PERSONA_USER_IDS


def test_enrichment_only_stable_users_with_photo_url() -> None:
    member = next(iter(STABLE_PERSONA_USER_IDS.values()))
    all_f = [
        {
            "id": member,
            "entity": "User",
            "data": {
                "id": member,
                "email": "agent@demo.dazzle.local",
                "name": "Alex",
                "role": "agent",
                "photo_url": "https://placehold.co/1.png",
            },
        },
        {
            "id": "other",
            "entity": "User",
            "data": {
                "id": "b2000000-0000-4000-8000-000000000099",
                "email": "x@demo.dazzle.local",
                "name": "X",
                "role": "agent",
                "photo_url": "https://placehold.co/2.png",
            },
        },
        {
            "id": "nophoto",
            "entity": "User",
            "data": {
                "id": member,
                "email": "agent@demo.dazzle.local",
                "name": "Alex",
                "role": "agent",
            },
        },
    ]
    # second row is non-stable; third lacks media — only first enriches
    out = _stable_user_media_enrichment(all_f)
    assert len(out) == 1
    assert out[0]["data"]["photo_url"].startswith("https://")
