"""Unit tests for exception handlers — JSON serialization of validation errors."""

import json
from typing import Annotated, Any
from unittest.mock import MagicMock

import pytest
from pydantic import AfterValidator, BaseModel, ValidationError


def _check_enum(v: str) -> str:
    if v not in ["low", "high"]:
        raise ValueError(f"Value '{v}' is not valid. Allowed: low, high")
    return v


class _FakeModel(BaseModel):
    priority: Annotated[str, AfterValidator(_check_enum)] = "low"


class TestValidationErrorHandler:
    """Test that validation_error_handler produces JSON-serializable responses."""

    @pytest.fixture
    def handler(self) -> Any:
        """Extract the validation_error_handler from register_exception_handlers."""
        from dazzle_back.runtime.exception_handlers import register_exception_handlers

        app = MagicMock()
        handlers: dict[type, Any] = {}

        def capture_handler(exc_class: type) -> Any:
            def decorator(fn: Any) -> Any:
                handlers[exc_class] = fn
                return fn

            return decorator

        app.exception_handler = capture_handler
        register_exception_handlers(app)
        return handlers[ValidationError]

    @pytest.mark.asyncio
    async def test_enum_validation_error_serializable(self, handler: Any) -> None:
        """ValueError from AfterValidator must not crash JSON serialization."""
        try:
            _FakeModel(priority="medium")
            pytest.fail("Should have raised ValidationError")
        except ValidationError as exc:
            response = await handler(MagicMock(), exc)

        assert response.status_code == 422
        body = json.loads(response.body)
        assert body["type"] == "validation_error"
        assert isinstance(body["detail"], list)
        assert len(body["detail"]) == 1
        err = body["detail"][0]
        assert err["type"] == "value_error"
        assert "priority" in err["loc"]
        # ctx.error should be a string, not a raw ValueError
        assert isinstance(err["ctx"]["error"], str)
        assert "Allowed: low, high" in err["ctx"]["error"]

    @pytest.mark.asyncio
    async def test_standard_validation_error_serializable(self, handler: Any) -> None:
        """Standard Pydantic required-field errors should also serialize cleanly."""

        class _Required(BaseModel):
            name: str

        try:
            _Required()  # type: ignore[call-arg]
            pytest.fail("Should have raised ValidationError")
        except ValidationError as exc:
            response = await handler(MagicMock(), exc)

        assert response.status_code == 422
        body = json.loads(response.body)
        assert body["type"] == "validation_error"
        assert len(body["detail"]) >= 1
        # Ensure the whole body is JSON-serializable (no crash)
        json.dumps(body)


# ============================================================================
# 404/403 dispatch (manwithacat/dazzle#776) — in-app vs marketing shell
# ============================================================================


class TestIsAppPath:
    """The _is_app_path helper decides which error template to render."""

    def test_root_is_not_app_path(self) -> None:
        from dazzle_back.runtime.exception_handlers import _is_app_path

        assert _is_app_path("/") is False

    def test_public_marketing_is_not_app_path(self) -> None:
        from dazzle_back.runtime.exception_handlers import _is_app_path

        assert _is_app_path("/about") is False
        assert _is_app_path("/pricing") is False
        assert _is_app_path("/login") is False

    def test_exact_app_root_is_app_path(self) -> None:
        from dazzle_back.runtime.exception_handlers import _is_app_path

        assert _is_app_path("/app") is True

    def test_app_subroute_is_app_path(self) -> None:
        from dazzle_back.runtime.exception_handlers import _is_app_path

        assert _is_app_path("/app/contact") is True
        assert _is_app_path("/app/contact/123") is True
        assert _is_app_path("/app/workspaces/contacts") is True

    def test_appfoo_is_not_app_path(self) -> None:
        """/application, /app_config etc. should NOT be treated as in-app."""
        from dazzle_back.runtime.exception_handlers import _is_app_path

        assert _is_app_path("/application") is False
        assert _is_app_path("/app_config") is False


class TestComputeBackAffordance:
    """The _compute_back_affordance helper builds parent-surface breadcrumbs."""

    def test_non_app_path_returns_none(self) -> None:
        from dazzle_back.runtime.exception_handlers import _compute_back_affordance

        assert _compute_back_affordance("/") is None
        assert _compute_back_affordance("/about") is None

    def test_app_root_returns_none(self) -> None:
        """No parent above /app itself."""
        from dazzle_back.runtime.exception_handlers import _compute_back_affordance

        assert _compute_back_affordance("/app") is None

    def test_surface_root_falls_back_to_dashboard(self) -> None:
        """/app/contact → parent is /app."""
        from dazzle_back.runtime.exception_handlers import _compute_back_affordance

        result = _compute_back_affordance("/app/contact")
        assert result == ("/app", "Back to Dashboard")

    def test_surface_record_falls_back_to_surface_list(self) -> None:
        """/app/contact/{id} → parent is /app/contact."""
        from dazzle_back.runtime.exception_handlers import _compute_back_affordance

        result = _compute_back_affordance("/app/contact/abc-123")
        assert result == ("/app/contact", "Back to List")

    def test_workspace_sub_falls_back_to_dashboard(self) -> None:
        """/app/workspaces/{foo} → parent is /app (not /app/workspaces)."""
        from dazzle_back.runtime.exception_handlers import _compute_back_affordance

        result = _compute_back_affordance("/app/workspaces/my_tickets")
        assert result == ("/app", "Back to Dashboard")


class TestLevenshtein:
    """Pure helper — shaves off a dependency on python-Levenshtein."""

    def test_equal_strings_distance_zero(self) -> None:
        from dazzle_back.runtime.exception_handlers import _levenshtein

        assert _levenshtein("task", "task") == 0

    def test_empty_strings_return_length(self) -> None:
        from dazzle_back.runtime.exception_handlers import _levenshtein

        assert _levenshtein("", "task") == 4
        assert _levenshtein("task", "") == 4

    def test_single_edit(self) -> None:
        from dazzle_back.runtime.exception_handlers import _levenshtein

        assert _levenshtein("task", "tasks") == 1
        assert _levenshtein("task", "tosk") == 1
        assert _levenshtein("task", "ta") == 2

    def test_transposition_is_two_edits(self) -> None:
        """Pure Levenshtein treats a transposition as 2 ops (del + insert)."""
        from dazzle_back.runtime.exception_handlers import _levenshtein

        assert _levenshtein("contact", "conatct") == 2


class TestCompute404Suggestions:
    """_compute_404_suggestions powers the friendly 404 (#811)."""

    def test_plural_flip_suggests_singular(self) -> None:
        from dazzle_back.runtime.exception_handlers import _compute_404_suggestions

        out = _compute_404_suggestions(
            "/app/tickets", entity_slugs=["ticket", "contact"], workspace_slugs=[]
        )
        assert out == [{"url": "/app/ticket", "label": "Ticket"}]

    def test_plural_flip_noop_when_singular_unknown(self) -> None:
        from dazzle_back.runtime.exception_handlers import _compute_404_suggestions

        out = _compute_404_suggestions("/app/horses", entity_slugs=["cow"], workspace_slugs=[])
        # "hors" is 4 edits from "cow" → beyond fuzzy threshold
        assert out == []

    def test_dashboard_alias_redirects_to_app_root(self) -> None:
        from dazzle_back.runtime.exception_handlers import _compute_404_suggestions

        assert _compute_404_suggestions("/dashboard", [], []) == [
            {"url": "/app", "label": "Dashboard"}
        ]
        assert _compute_404_suggestions("/app/dashboard", [], []) == [
            {"url": "/app", "label": "Dashboard"}
        ]

    def test_fuzzy_match_catches_typo(self) -> None:
        from dazzle_back.runtime.exception_handlers import _compute_404_suggestions

        out = _compute_404_suggestions(
            "/app/conatct", entity_slugs=["contact", "task"], workspace_slugs=[]
        )
        assert {"url": "/app/contact", "label": "Contact"} in out

    def test_workspace_fuzzy_match(self) -> None:
        from dazzle_back.runtime.exception_handlers import _compute_404_suggestions

        out = _compute_404_suggestions(
            "/app/workspaces/command_cnter",
            entity_slugs=[],
            workspace_slugs=["command_center", "ops_hub"],
        )
        assert any(s["url"] == "/app/workspaces/command_center" for s in out)

    def test_unrelated_path_returns_empty(self) -> None:
        from dazzle_back.runtime.exception_handlers import _compute_404_suggestions

        assert (
            _compute_404_suggestions(
                "/app/xyzabc", entity_slugs=["task", "contact"], workspace_slugs=[]
            )
            == []
        )

    def test_results_are_capped_at_three(self) -> None:
        from dazzle_back.runtime.exception_handlers import _compute_404_suggestions

        # Five entity slugs all within edit distance 2 of "tas"
        out = _compute_404_suggestions(
            "/app/tas",
            entity_slugs=["task", "tast", "taxi", "tan", "tag"],
            workspace_slugs=[],
        )
        assert len(out) <= 3

    def test_trailing_slash_is_normalised(self) -> None:
        from dazzle_back.runtime.exception_handlers import _compute_404_suggestions

        out = _compute_404_suggestions("/app/tickets/", entity_slugs=["ticket"], workspace_slugs=[])
        assert out == [{"url": "/app/ticket", "label": "Ticket"}]


class TestErrorHandlerDispatch:
    """The registered 404/403 handler chooses templates by URL prefix."""

    @pytest.fixture
    def handler(self) -> Any:
        from dazzle_back.runtime.exception_handlers import register_site_error_handlers

        app = MagicMock()
        handlers: dict[type, Any] = {}

        def capture_handler(exc_class: type) -> Any:
            def decorator(fn: Any) -> Any:
                handlers[exc_class] = fn
                return fn

            return decorator

        app.exception_handler = capture_handler
        register_site_error_handlers(app, sitespec_data={"product_name": "TestApp"})

        from starlette.exceptions import HTTPException as StarletteHTTPException

        return handlers[StarletteHTTPException]

    def _make_request(self, path: str, accept: str = "text/html") -> Any:
        req = MagicMock()
        req.headers = {"accept": accept}
        req.url = MagicMock()
        req.url.path = path
        # `str(request.url.path)` is used by the handler code
        req.url.__str__ = lambda self: f"http://test{path}"  # type: ignore[method-assign]
        return req

    @pytest.mark.asyncio
    async def test_404_on_app_path_renders_app_shell(self, handler: Any) -> None:
        """404 under /app/* should render the in-app shell, not the marketing site."""
        from starlette.exceptions import HTTPException

        req = self._make_request("/app/contact/bad-id")
        exc = HTTPException(status_code=404, detail="Not Found")

        response = await handler(req, exc)

        assert response.status_code == 404
        body = response.body.decode()
        # In-app shell markers — the app_shell layout renders a <aside>
        # (sidebar) plus the 404 h1 inside the page body.
        assert "<h1" in body and "404" in body
        assert "<aside" in body  # app_shell sidebar present
        # Back affordance to /app/contact (parent list)
        assert 'href="/app/contact"' in body
        assert "Back to List" in body
        # MUST NOT contain marketing nav links
        assert "site/includes/nav.html" not in body
        assert "Get Started" not in body

    @pytest.mark.asyncio
    async def test_404_on_marketing_path_renders_site(self, handler: Any) -> None:
        """404 under public paths should render the marketing-site 404."""
        from starlette.exceptions import HTTPException

        req = self._make_request("/about/bad")
        exc = HTTPException(status_code=404, detail="Not Found")

        response = await handler(req, exc)

        assert response.status_code == 404
        body = response.body.decode()
        # Marketing site 404 uses the dz-404 classes
        assert "dz-404" in body

    @pytest.mark.asyncio
    async def test_403_on_app_path_renders_app_shell(self, handler: Any) -> None:
        """403 under /app/* should also render the in-app shell."""
        from starlette.exceptions import HTTPException

        req = self._make_request("/app/workspaces/my_tickets")
        exc = HTTPException(status_code=403, detail="You don't have permission")

        response = await handler(req, exc)

        assert response.status_code == 403
        body = response.body.decode()
        assert "403" in body
        assert "<aside" in body
        # Back to dashboard (workspace parent rule)
        assert 'href="/app"' in body
        assert "Back to Dashboard" in body
        # Custom message from exc.detail
        assert "You don&#39;t have permission" in body or "You don't have permission" in body

    @pytest.mark.asyncio
    async def test_api_request_still_returns_json(self, handler: Any) -> None:
        """Non-browser requests should always get JSON, regardless of path."""
        from starlette.exceptions import HTTPException

        req = self._make_request("/app/contact/bad", accept="application/json")
        exc = HTTPException(status_code=404, detail="Not Found")

        response = await handler(req, exc)

        assert response.status_code == 404
        body = json.loads(response.body)
        assert body["detail"] == "Not Found"
