"""Tests for the sitespec MCP handlers."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_CONFTEST_PATH = str(Path(__file__).parent / "conftest.py")


def _load_conftest_helper(name: str) -> object:
    """Load a helper from conftest.py by file path (not package import)."""
    spec = importlib.util.spec_from_file_location("_mcp_conftest", _CONFTEST_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, name)


def _import_sitespec():
    """Import sitespec handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports
    install_handlers_common_mock = _load_conftest_helper("install_handlers_common_mock")

    sys.modules["dazzle.mcp.server.handlers"] = MagicMock(pytest_plugins=[])
    install_handlers_common_mock()

    # Mock sitespec data structures
    mock_nav_item = SimpleNamespace(label="Home", href="/")
    mock_footer_column = SimpleNamespace(
        title="Links",
        links=[SimpleNamespace(label="About", href="/about")],
    )
    mock_page = SimpleNamespace(
        route="/",
        type=SimpleNamespace(value="landing"),
        title="Home",
        sections=[],
        source=None,
    )
    mock_logo = SimpleNamespace(
        mode=SimpleNamespace(value="text"),
        text="My App",
        image_path=None,
    )
    mock_brand = SimpleNamespace(
        product_name="My App",
        tagline="Your best solution",
        support_email="support@example.com",
        company_legal_name="My Company",
        logo=mock_logo,
    )
    mock_layout = SimpleNamespace(
        theme=SimpleNamespace(value="light"),
        auth=SimpleNamespace(primary_entry="login"),
        nav=SimpleNamespace(
            public=[mock_nav_item],
            authenticated=[mock_nav_item],
        ),
        footer=SimpleNamespace(
            columns=[mock_footer_column],
            disclaimer="© 2025 My Company",
        ),
    )
    mock_legal = SimpleNamespace(
        terms=SimpleNamespace(route="/terms"),
        privacy=SimpleNamespace(route="/privacy"),
    )
    mock_auth_pages = SimpleNamespace(
        login=SimpleNamespace(route="/login", enabled=True),
        signup=SimpleNamespace(route="/signup", enabled=True),
    )
    mock_integrations = SimpleNamespace(
        app_mount_route="/app",
        auth_provider=SimpleNamespace(value="internal"),
    )

    mock_sitespec = SimpleNamespace(
        version="1.0",
        brand=mock_brand,
        layout=mock_layout,
        pages=[mock_page],
        legal=mock_legal,
        auth_pages=mock_auth_pages,
        integrations=mock_integrations,
        get_all_routes=lambda: ["/", "/login", "/signup", "/terms", "/privacy"],
        model_dump=lambda: {"version": "1.0"},
    )

    mock_sitespec_loader = MagicMock()
    mock_sitespec_loader.load_sitespec = MagicMock(return_value=mock_sitespec)
    mock_sitespec_loader.sitespec_exists = MagicMock(return_value=True)
    mock_sitespec_loader.SiteSpecError = Exception
    mock_sitespec_loader.validate_sitespec = MagicMock(
        return_value=SimpleNamespace(
            is_valid=True,
            errors=[],
            warnings=["Consider adding more content"],
        )
    )
    mock_sitespec_loader.scaffold_site = MagicMock(
        return_value={"sitespec": Path("sitespec.yaml"), "content": []}
    )
    mock_sitespec_loader.copy_file_exists = MagicMock(return_value=False)
    mock_sitespec_loader.get_copy_file_path = MagicMock(return_value=Path("site/content/copy.md"))
    mock_sitespec_loader.load_copy = MagicMock(return_value=None)
    mock_sitespec_loader.scaffold_copy_file = MagicMock(return_value=Path("site/content/copy.md"))
    sys.modules["dazzle.core.sitespec_loader"] = mock_sitespec_loader

    # Mock copy_parser
    mock_copy_parser = MagicMock()
    mock_copy_parser.load_copy_file = MagicMock(return_value=None)
    sys.modules["dazzle.core.copy_parser"] = mock_copy_parser

    # Mock site_coherence
    mock_coherence = MagicMock()
    mock_report = MagicMock()
    mock_report.to_dict = MagicMock(
        return_value={
            "score": 85,
            "error_count": 0,
            "warning_count": 1,
        }
    )
    mock_report.format = MagicMock(return_value="Site coherence: 85%")
    mock_report.error_count = 0
    mock_report.warning_count = 1
    mock_coherence.validate_site_coherence = MagicMock(return_value=mock_report)
    sys.modules["dazzle.core.site_coherence"] = mock_coherence

    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "sitespec.py"
    )
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.sitespec",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
    sys.modules["dazzle.mcp.server.handlers.sitespec"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_ss = _import_sitespec()
_LOADER = sys.modules["dazzle.core.sitespec_loader"]
_COHERENCE = sys.modules["dazzle.core.site_coherence"]

# Get references to the functions we need
get_sitespec_handler = _ss.get_sitespec_handler
validate_sitespec_handler = _ss.validate_sitespec_handler
scaffold_site_handler = _ss.scaffold_site_handler
get_copy_handler = _ss.get_copy_handler
scaffold_copy_handler = _ss.scaffold_copy_handler
review_copy_handler = _ss.review_copy_handler
coherence_handler = _ss.coherence_handler
advise_sitespec_handler = _ss.advise_sitespec_handler


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project with minimal structure."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Create dazzle.toml manifest
    manifest = project_dir / "dazzle.toml"
    manifest.write_text(
        """
[project]
name = "test_project"
version = "0.1.0"
root = "test_project"

[modules]
paths = ["./dsl"]
"""
    )

    # Create site directory
    site_dir = project_dir / "site" / "content"
    site_dir.mkdir(parents=True)

    return project_dir


# =============================================================================
# Handler Tests
# =============================================================================


@pytest.mark.parametrize("use_defaults", [True, False], ids=["defaults", "no-defaults"])
def test_get_sitespec_serialises_spec(temp_project, use_defaults: bool) -> None:
    data = json.loads(get_sitespec_handler(temp_project, {"use_defaults": use_defaults}))
    _LOADER.load_sitespec.assert_called_with(temp_project, use_defaults=use_defaults)
    assert data["version"] == "1.0"
    assert data["brand"]["product_name"] == "My App"
    assert data["brand"]["tagline"] == "Your best solution"
    assert data["layout"]["nav"]["public"] == [{"label": "Home", "href": "/"}]
    assert data["pages"] == [
        {"route": "/", "type": "landing", "title": "Home", "sections_count": 0, "source": None}
    ]
    assert data["all_routes"] == ["/", "/login", "/signup", "/terms", "/privacy"]


@pytest.mark.parametrize("check", [True, False], ids=["check-content", "skip-content"])
def test_validate_sitespec_reports_counts(temp_project, check: bool) -> None:
    data = json.loads(validate_sitespec_handler(temp_project, {"check_content_files": check}))
    assert data == {
        "is_valid": True,
        "error_count": 0,
        "warning_count": 1,
        "errors": [],
        "warnings": ["Consider adding more content"],
    }
    assert _LOADER.validate_sitespec.call_args.kwargs["check_content_files"] is check


@pytest.mark.parametrize(
    ("args", "product_name", "overwrite"),
    [
        pytest.param({}, "My App", False, id="defaults"),
        pytest.param({"product_name": "My Product"}, "My Product", False, id="product-name"),
        pytest.param({"overwrite": True}, "My App", True, id="overwrite"),
    ],
)
def test_scaffold_site(temp_project, args: dict, product_name: str, overwrite: bool) -> None:
    data = json.loads(scaffold_site_handler(temp_project, args))
    _LOADER.scaffold_site.assert_called_with(temp_project, product_name, overwrite=overwrite)
    assert data["success"] is True
    assert data["product_name"] == product_name
    assert "sitespec.yaml" in data["created_files"]
    # The static/images/ convention directory is created with a .gitkeep.
    assert (temp_project / "static" / "images" / ".gitkeep").exists()


def test_copy_handlers_when_copy_md_missing(temp_project, monkeypatch) -> None:
    monkeypatch.setattr(_LOADER, "copy_file_exists", MagicMock(return_value=False))
    got = json.loads(get_copy_handler(temp_project, {}))
    assert got["exists"] is False
    assert "scaffold_copy" in got["hint"]
    assert json.loads(review_copy_handler(temp_project, {}))["exists"] is False
    created = json.loads(scaffold_copy_handler(temp_project, {}))
    assert created["success"] is True
    assert created["overwritten"] is False
    assert created["sections"][0] == "Hero"


def test_get_copy_formats_sections(temp_project, monkeypatch) -> None:
    monkeypatch.setattr(_LOADER, "copy_file_exists", MagicMock(return_value=True))
    monkeypatch.setattr(
        _LOADER,
        "load_copy",
        MagicMock(return_value={"sections": [{"type": "hero", "title": "Welcome"}]}),
    )
    data = json.loads(get_copy_handler(temp_project, {}))
    assert data["exists"] is True
    assert data["section_count"] == 1
    assert data["sections"] == [{"type": "hero", "title": "Welcome"}]


# An existing copy.md is never overwritten unless overwrite=true is passed.
@pytest.mark.parametrize(
    ("overwrite", "success"),
    [pytest.param(False, False, id="refused-by-default"), pytest.param(True, True, id="overwrite")],
)
def test_scaffold_copy_existing_file(temp_project, monkeypatch, overwrite, success) -> None:
    monkeypatch.setattr(_LOADER, "copy_file_exists", MagicMock(return_value=True))
    data = json.loads(scaffold_copy_handler(temp_project, {"overwrite": overwrite}))
    assert data["success"] is success
    if overwrite:
        assert data["overwritten"] is True
    else:
        assert "Overwriting will lose existing content" in data["warning"]


@pytest.mark.parametrize("args", [{}, {"business_context": "saas"}], ids=["plain", "saas-context"])
def test_coherence_reports_score_and_priority(temp_project, args: dict) -> None:
    data = json.loads(coherence_handler(temp_project, args))
    assert data["score"] == 85
    assert data["formatted"] == "Site coherence: 85%"
    assert "priority" in data
    assert _COHERENCE.validate_site_coherence.call_args.kwargs.get("business_context") == args.get(
        "business_context"
    )


def test_advise_sitespec_summary(temp_project) -> None:
    data = json.loads(advise_sitespec_handler(temp_project, {}))
    # The mock model_dump() carries no pages, so only site-level advice remains.
    assert data["page_count"] == 0
    assert data["total_suggestions"] == 1
    assert "summary" in data
