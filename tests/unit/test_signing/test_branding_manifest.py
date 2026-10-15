"""Manifest ``[signing]`` parsing and the PdfBranding wire-up (#1283 phase 8).

``ServerState._resolve_pdf_branding`` falls back in three tiers:
``[signing] organisation`` → full branding; ``[project] name`` → minimal
``PdfBranding(organisation=name)``; nothing → ``None`` (the router's
built-in default).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.core.manifest import SigningConfig, load_manifest
from dazzle.http.runtime.server import DazzleBackendApp
from dazzle.signing.service import PdfBranding

_PROJECT = '[project]\nname = "Test Project"\nversion = "0.0.0"\n\n'
_MODULES = '[modules]\npaths = ["./dsl"]\n'


def _write(tmp_path: Path, signing: str, *, project: str = _PROJECT) -> Path:
    path = tmp_path / "dazzle.toml"
    path.write_text(project + _MODULES + textwrap.dedent(signing))
    return path


_DEFAULTS = {
    "organisation": "",
    "tagline": "",
    "footer_text": "",
    "location": "United Kingdom",
    "support_contact": "",
    "resend_hook": "",
}


@pytest.mark.parametrize(
    ("block", "overrides"),
    [
        pytest.param("", {}, id="absent-block-all-defaults"),
        pytest.param(
            """
            [signing]
            organisation = "Acme Ltd"
            tagline = "Chartered Accountants"
            footer_text = "Acme Ltd | Registered in England & Wales"
            location = "England and Wales"
            """,
            {
                "organisation": "Acme Ltd",
                "tagline": "Chartered Accountants",
                "footer_text": "Acme Ltd | Registered in England & Wales",
                "location": "England and Wales",
            },
            id="full-block",
        ),
        pytest.param(
            '\n[signing]\norganisation = "Acme Ltd"\n',
            {"organisation": "Acme Ltd"},
            # location stays "United Kingdom", not empty
            id="partial-block-keeps-defaults",
        ),
        pytest.param(
            '\n[signing]\norganisation = "Acme Ltd"\nnotes = "Annotated for ops"\n',
            {"organisation": "Acme Ltd"},
            id="unknown-keys-ignored",
        ),
        pytest.param(
            '\n[signing]\nsupport_contact = "help@acme.example"\n'
            'resend_hook = "app.signing.resend.deliver"\n',
            {"support_contact": "help@acme.example", "resend_hook": "app.signing.resend.deliver"},
            id="recovery-keys-TR-53",
        ),
    ],
)
def test_signing_block(block: str, overrides: dict[str, str], tmp_path: Path) -> None:
    signing = load_manifest(_write(tmp_path, block)).signing
    assert isinstance(signing, SigningConfig)
    assert {k: getattr(signing, k) for k in _DEFAULTS} == {**_DEFAULTS, **overrides}


def _resolve(project_root: Path | None) -> PdfBranding | None:
    # The method reads only ``self._project_root``.
    stub: Any = SimpleNamespace(_project_root=project_root)
    return DazzleBackendApp._resolve_pdf_branding(stub)


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        pytest.param(None, None, id="no-project-root"),
        pytest.param("", None, id="no-manifest-file"),
        pytest.param(
            (
                _PROJECT,
                '\n[signing]\norganisation = "Acme Ltd"\ntagline = "Chartered Accountants"\n'
                'footer_text = "Acme Ltd | EW"\nlocation = "England and Wales"\n',
            ),
            PdfBranding(
                organisation="Acme Ltd",
                organisation_tagline="Chartered Accountants",
                footer_text="Acme Ltd | EW",
                location="England and Wales",
            ),
            id="signing-block-drives-full-branding",
        ),
        pytest.param(
            (_PROJECT, ""),
            # Only the organisation is wired; the rest are PdfBranding defaults.
            PdfBranding(
                organisation="Test Project",
                organisation_tagline="",
                footer_text="",
                location="United Kingdom",
            ),
            id="project-name-fallback",
        ),
        # The manifest defaults name to "unnamed" — not a useful brand, so the
        # router keeps its built-in "Dazzle App".
        pytest.param(("", ""), None, id="unnamed-project-returns-none"),
    ],
)
def test_resolve_pdf_branding(
    manifest: tuple[str, str] | str | None, expected: PdfBranding | None, tmp_path: Path
) -> None:
    if isinstance(manifest, tuple):
        project, signing = manifest
        _write(tmp_path, signing, project=project)
    assert _resolve(None if manifest is None else tmp_path) == expected
