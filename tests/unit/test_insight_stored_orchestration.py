from dazzle.http.runtime.insight_store import reset_insight_provider, set_insight_provider
from dazzle.http.runtime.workspace_region_orchestration import _read_stored_insight
from dazzle.render.fragment.insight import StoredInsight


def test_read_stored_insight_returns_provider_value() -> None:
    si = StoredInsight(prose=("x",), confidence="high", generated_at="2026-06-25")
    set_insight_provider(lambda r: si)
    try:
        assert _read_stored_insight("r") is si
    finally:
        reset_insight_provider()


def test_read_stored_insight_swallows_provider_error() -> None:
    def _boom(_r: str):
        raise RuntimeError("provider down")

    set_insight_provider(_boom)
    try:
        assert _read_stored_insight("r") is None  # error → None → deterministic fallback
    finally:
        reset_insight_provider()
