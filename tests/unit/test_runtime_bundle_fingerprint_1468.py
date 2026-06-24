"""#1468: the framework runtime bundle must propagate fixes to returning users.

The page-runtime JS/CSS bundle (`/static/dist/dazzle.min.{js,css}`) was emitted
non-fingerprinted with a multi-hour `max-age`, so after a deploy returning
visitors kept running the cached old bundle (the #1465 dzTable crash "didn't
take" for ~4h). The fix content-hashes the bundle URLs in production/staging
(immutable + instant propagation) and adds a `[ui] active_development` opt-out
(no-cache iteration) + a configurable `[ui] static_max_age`.

Fingerprinting is env-gated (mirrors `should_bundle_assets`) so dev/test see
plain URLs — both for fast iteration and stable assertions.
"""

import tempfile
from pathlib import Path

import pytest

from dazzle.page.runtime.asset_fingerprint import (
    FINGERPRINT_RE,
    fingerprint_static_url,
    should_fingerprint,
)

# --------------------------------------------------------------------------- #
# should_fingerprint — the environment / active-development gate
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("env", "active_dev", "expected"),
    [
        ("production", False, True),
        ("staging", False, True),
        ("", False, False),  # dev / unset
        ("development", False, False),
        ("production", True, False),  # active_development opts out even in prod
        ("staging", True, False),
    ],
)
def test_should_fingerprint_gate(env: str, active_dev: bool, expected: bool) -> None:
    assert should_fingerprint(active_development=active_dev, env=env) is expected


# --------------------------------------------------------------------------- #
# fingerprint_static_url — URL rewriting (gated)
# --------------------------------------------------------------------------- #


def test_bundle_url_is_fingerprinted_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAZZLE_ENV", "production")
    out = fingerprint_static_url("/static/dist/dazzle.min.js")
    assert out != "/static/dist/dazzle.min.js", "bundle URL was not fingerprinted in production"
    assert FINGERPRINT_RE.search(out.rsplit("/", 1)[-1]), f"no content hash in {out!r}"
    assert out.startswith("/static/dist/dazzle.min.") and out.endswith(".js")


def test_bundle_url_is_plain_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAZZLE_ENV", "")
    assert fingerprint_static_url("/static/dist/dazzle.min.js") == "/static/dist/dazzle.min.js"


def test_active_development_disables_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAZZLE_ENV", "production")
    assert (
        fingerprint_static_url("/static/dist/dazzle.min.js", active_development=True)
        == "/static/dist/dazzle.min.js"
    )


def test_unknown_and_nonstatic_urls_pass_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAZZLE_ENV", "production")
    # Not in the framework manifest → unchanged (served at the default max-age).
    assert (
        fingerprint_static_url("/static/dist/nope-not-real.js") == "/static/dist/nope-not-real.js"
    )
    # Not a /static/ URL → unchanged.
    assert fingerprint_static_url("https://cdn.example/x.js") == "https://cdn.example/x.js"


# --------------------------------------------------------------------------- #
# resolve_app_chrome — the dominant emission path
# --------------------------------------------------------------------------- #


def test_app_chrome_emits_fingerprinted_bundle_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DAZZLE_ENV", "production")
    from dazzle.page.runtime.app_chrome import resolve_app_chrome

    chrome = resolve_app_chrome(None, manifest=None)
    js = "\n".join(chrome.js_scripts)
    css = "\n".join(chrome.css_links)
    assert "/static/dist/dazzle.min.js" not in chrome.js_scripts, "JS bundle not fingerprinted"
    assert "/static/dist/dazzle.min.css" not in chrome.css_links, "CSS bundle not fingerprinted"
    assert any(
        FINGERPRINT_RE.search(u.rsplit("/", 1)[-1]) for u in chrome.js_scripts if "dazzle.min" in u
    )
    assert "dazzle.min." in js and "dazzle.min." in css


def test_app_chrome_plain_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAZZLE_ENV", "")
    from dazzle.page.runtime.app_chrome import resolve_app_chrome

    chrome = resolve_app_chrome(None, manifest=None)
    assert "/static/dist/dazzle.min.js" in chrome.js_scripts
    assert "/static/dist/dazzle.min.css" in chrome.css_links


# --------------------------------------------------------------------------- #
# [ui] manifest parsing (Part B config)
# --------------------------------------------------------------------------- #


def _load(toml_body: str) -> object:
    from dazzle.core.manifest import load_manifest

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "dazzle.toml"
        p.write_text(toml_body)
        return load_manifest(p)


def test_ui_active_development_and_max_age_parse() -> None:
    mf = _load("[ui]\nactive_development = true\nstatic_max_age = 300\n")
    assert mf.active_development is True
    assert mf.static_max_age == 300


def test_ui_defaults() -> None:
    mf = _load("[project]\nname = 'x'\n")
    assert mf.active_development is False
    assert mf.static_max_age is None


def test_ui_static_max_age_rejects_negative() -> None:
    with pytest.raises(ValueError, match="static_max_age"):
        _load("[ui]\nstatic_max_age = -1\n")


# --------------------------------------------------------------------------- #
# CombinedStaticFiles — cache-control policy (Part B serving)
# --------------------------------------------------------------------------- #


def _serve_cache_control(filename: str, request_path: str, **kw: object) -> str:
    from dazzle.http.runtime.static_files import CombinedStaticFiles

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / filename).write_text("/* x */")
        sf = CombinedStaticFiles(directories=[root], **kw)  # type: ignore[arg-type]
        full = root / filename
        scope = {"method": "GET", "headers": [], "path": request_path}
        resp = sf.file_response(str(full), (full).stat(), scope)
        return resp.headers.get("cache-control", "")


def test_active_development_serves_no_cache() -> None:
    cc = _serve_cache_control(
        "dazzle.min.js", "/static/dist/dazzle.min.js", active_development=True
    )
    assert cc == "no-cache"


def test_configured_max_age_for_non_fingerprinted_non_bundle() -> None:
    # A non-bundle static asset (not under /dist/) honours the configured max-age.
    cc = _serve_cache_control("logo.png", "/static/img/logo.png", default_max_age=300)
    assert cc == "public, max-age=300"


def test_runtime_bundle_no_cache_when_requested_unfingerprinted() -> None:
    # #1468 safety net: an emission site that hardcodes the plain /dist/ URL
    # (not wired to fingerprint) still propagates fixes — served no-cache, not
    # the multi-hour default. Covers both the mounted (/static/dist/...) and
    # mount-stripped (/dist/...) request-path shapes.
    for req in ("/static/dist/dazzle.min.js", "/dist/dazzle.min.css"):
        cc = _serve_cache_control("dazzle.min.js", req, default_max_age=3600)
        assert cc == "no-cache", f"{req} should be no-cache, got {cc!r}"


def test_fingerprinted_request_is_immutable() -> None:
    # The requested path carries the hash; the file on disk is the original.
    cc = _serve_cache_control("dazzle.min.js", "/static/dist/dazzle.min.a1b2c3d4.js")
    assert "immutable" in cc and "max-age=31536000" in cc
