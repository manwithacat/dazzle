from dazzle.http.runtime.insight_store import (
    get_stored_insight,
    reset_insight_provider,
    set_insight_provider,
)
from dazzle.render.fragment.insight import StoredInsight


def test_default_provider_returns_none() -> None:
    reset_insight_provider()
    assert get_stored_insight("any_region") is None


def test_settable_provider() -> None:
    si = StoredInsight(
        prose=("Revenue is climbing.",), confidence="high", generated_at="2026-06-25"
    )
    set_insight_provider(lambda region: si if region == "team_insight" else None)
    try:
        assert get_stored_insight("team_insight") is si
        assert get_stored_insight("other") is None
    finally:
        reset_insight_provider()
