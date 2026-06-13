"""Manifest [signing] parsing + PdfBranding wire-up (#1283 phase 8).

Covers two layers:

  - ``load_manifest`` produces a ``SigningConfig`` from a
    ``[signing]`` block in ``dazzle.toml``, with sensible defaults
    when keys are absent.
  - ``ServerState._resolve_pdf_branding`` produces a ``PdfBranding``
    from the loaded manifest, with three-tier fallback:
      1. ``[signing] organisation`` set → full quartet.
      2. ``[project] name`` set → minimal ``PdfBranding(organisation=name)``.
      3. Nothing set → ``None`` (router falls back to its built-in default).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from dazzle.core.manifest import SigningConfig, load_manifest


def _write_manifest(tmp_path: Path, body: str) -> Path:
    """Write a minimal manifest with the supplied body appended."""
    text = textwrap.dedent(
        """
        [project]
        name = "Test Project"
        version = "0.0.0"

        [modules]
        paths = ["./dsl"]
        """
    ).lstrip()
    text += textwrap.dedent(body)
    manifest_path = tmp_path / "dazzle.toml"
    manifest_path.write_text(text)
    return manifest_path


# -- Manifest parsing --------------------------------------------------


class TestSigningConfigParsing:
    def test_signing_block_absent_yields_defaults(self, tmp_path: Path) -> None:
        manifest = load_manifest(_write_manifest(tmp_path, ""))
        assert manifest.signing == SigningConfig()
        # Sanity: defaults are project-neutral.
        assert manifest.signing.organisation == ""
        assert manifest.signing.tagline == ""
        assert manifest.signing.footer_text == ""
        assert manifest.signing.location == "United Kingdom"

    def test_signing_block_full(self, tmp_path: Path) -> None:
        manifest = load_manifest(
            _write_manifest(
                tmp_path,
                """
                [signing]
                organisation = "Acme Ltd"
                tagline = "Chartered Accountants"
                footer_text = "Acme Ltd | Registered in England & Wales"
                location = "England and Wales"
                """,
            )
        )
        assert manifest.signing.organisation == "Acme Ltd"
        assert manifest.signing.tagline == "Chartered Accountants"
        assert manifest.signing.footer_text == "Acme Ltd | Registered in England & Wales"
        assert manifest.signing.location == "England and Wales"

    def test_signing_recovery_keys_parsed(self, tmp_path: Path) -> None:
        """TR-53: support_contact + resend_hook flow off the [signing] block,
        defaulting to empty when absent."""
        assert SigningConfig().support_contact == ""
        assert SigningConfig().resend_hook == ""
        manifest = load_manifest(
            _write_manifest(
                tmp_path,
                """
                [signing]
                support_contact = "help@acme.example"
                resend_hook = "app.signing.resend.deliver"
                """,
            )
        )
        assert manifest.signing.support_contact == "help@acme.example"
        assert manifest.signing.resend_hook == "app.signing.resend.deliver"

    def test_signing_block_partial(self, tmp_path: Path) -> None:
        """Missing keys take the SigningConfig defaults — location
        stays 'United Kingdom' rather than collapsing to empty."""
        manifest = load_manifest(
            _write_manifest(
                tmp_path,
                """
                [signing]
                organisation = "Acme Ltd"
                """,
            )
        )
        assert manifest.signing.organisation == "Acme Ltd"
        assert manifest.signing.tagline == ""
        assert manifest.signing.footer_text == ""
        assert manifest.signing.location == "United Kingdom"

    def test_signing_block_ignores_unknown_keys(self, tmp_path: Path) -> None:
        """Unknown keys don't crash parsing — projects can include
        annotations / future fields without tripping the loader."""
        manifest = load_manifest(
            _write_manifest(
                tmp_path,
                """
                [signing]
                organisation = "Acme Ltd"
                notes = "Annotated for ops"
                """,
            )
        )
        assert manifest.signing.organisation == "Acme Ltd"


# -- PdfBranding resolver ----------------------------------------------


class _StubServer:
    """ServerState-shaped stub carrying only the fields
    ``_resolve_pdf_branding`` reads."""

    _project_root: Path | None


def _build_server_state_stub(project_root: Path | None) -> _StubServer:
    stub = _StubServer()
    stub._project_root = project_root
    return stub


def _resolve(stub: object):
    """Invoke the unbound method against a stub. The method only
    touches ``self._project_root`` and stateless imports."""
    from dazzle.back.runtime.server import DazzleBackendApp

    return DazzleBackendApp._resolve_pdf_branding(stub)  # type: ignore[arg-type]


class TestBrandingResolver:
    def test_no_project_root_returns_none(self) -> None:
        result = _resolve(_build_server_state_stub(None))
        assert result is None

    def test_no_manifest_returns_none(self, tmp_path: Path) -> None:
        result = _resolve(_build_server_state_stub(tmp_path))
        assert result is None

    def test_signing_block_drives_full_branding(self, tmp_path: Path) -> None:
        _write_manifest(
            tmp_path,
            """
            [signing]
            organisation = "Acme Ltd"
            tagline = "Chartered Accountants"
            footer_text = "Acme Ltd | EW"
            location = "England and Wales"
            """,
        )
        result = _resolve(_build_server_state_stub(tmp_path))
        assert result is not None
        assert result.organisation == "Acme Ltd"
        assert result.organisation_tagline == "Chartered Accountants"
        assert result.footer_text == "Acme Ltd | EW"
        assert result.location == "England and Wales"

    def test_project_name_fallback_when_signing_block_absent(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, "")  # no [signing] block
        result = _resolve(_build_server_state_stub(tmp_path))
        assert result is not None
        assert result.organisation == "Test Project"
        # Tagline + footer stay defaults — the minimal fallback only
        # wires the organisation name.
        assert result.organisation_tagline == ""
        assert result.footer_text == ""

    def test_unnamed_project_returns_none(self, tmp_path: Path) -> None:
        """The manifest defaults `name` to 'unnamed' when omitted;
        that's not a useful branding string, so the resolver returns
        None to let the router fall back to its built-in 'Dazzle App'."""
        manifest_path = tmp_path / "dazzle.toml"
        manifest_path.write_text(
            textwrap.dedent(
                """
                [modules]
                paths = ["./dsl"]
                """
            ).lstrip()
        )
        result = _resolve(_build_server_state_stub(tmp_path))
        assert result is None
