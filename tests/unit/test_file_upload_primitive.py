"""Issue #1033 (v0.66.140): regression tests for the FileUpload
primitive — closes the last cyfuture pilot blocker.

Pre-fix, the Fragment adapter's `_field_to_primitive` had no branch
for `kind == "file"` — five cyfuture surfaces (Document, EngagementLetter,
VerificationEvidence variants) were stuck on the legacy Jinja path.
Fragment-audit explicitly flagged this as
`unsupported_field_type: file`.

Fix: new `FileUpload` primitive in `forms.py` mirroring `RefPicker`'s
shape; renderer emits the legacy file-widget DOM contract
(`<div data-dz-widget="file-upload">` + hidden FK input); adapter
dispatches on `kind == "file"`; coverage's
`_UNSUPPORTED_FIELD_TYPES` set drops `"file"` so the audit now
reports zero blockers."""

from __future__ import annotations

import pytest

from dazzle.http.runtime.renderers.fragment_adapter import _field_to_primitive
from dazzle.render.fragment import URL, FileUpload, FragmentRenderer
from dazzle.render.fragment.coverage import _UNSUPPORTED_FIELD_TYPES

# ── Primitive validation ──


def test_file_upload_validates_required_fields() -> None:
    """Empty `name` / `label` / negative `max_size_bytes` all raise."""
    with pytest.raises(ValueError, match="non-empty name"):
        FileUpload(name="", label="X", upload_url=URL("/u"))
    with pytest.raises(ValueError, match="non-empty label"):
        FileUpload(name="f", label="", upload_url=URL("/u"))
    with pytest.raises(ValueError, match="max_size_bytes"):
        FileUpload(name="f", label="F", upload_url=URL("/u"), max_size_bytes=-1)


def test_file_upload_defaults_clean() -> None:
    """Default required=False, accept="", max_size_bytes=0,
    initial_value="", initial_label="" — minimal-construction works."""
    fu = FileUpload(name="f", label="F", upload_url=URL("/u"))
    assert fu.required is False
    assert fu.accept == ""
    assert fu.max_size_bytes == 0
    assert fu.initial_value == ""
    assert fu.initial_label == ""


# ── Renderer emit ──


def test_file_upload_emits_widget_drop_zone_attrs() -> None:
    """The outer wrapper carries `data-dz-widget="file-upload"` +
    `data-dz-target="<upload_url>"` — the contract the Alpine
    `dz.fileUpload` controller reads."""
    html = FragmentRenderer().render(
        FileUpload(name="doc", label="Document", upload_url=URL("/uploads/docs"))
    )
    assert 'data-dz-widget="file-upload"' in html
    assert 'data-dz-target="/uploads/docs"' in html


def test_file_upload_emits_hidden_fk_input_with_dz_attrs() -> None:
    """Hidden `<input>` is the source of truth for the form post —
    carries `data-dazzle-field` + `data-dz-file-value` so Alpine can
    write the file URL/key back into it after upload."""
    html = FragmentRenderer().render(
        FileUpload(name="document_file", label="Doc", upload_url=URL("/u"))
    )
    assert 'type="hidden" name="document_file"' in html
    assert 'id="field-document_file"' in html
    assert 'data-dazzle-field="document_file"' in html
    assert "data-dz-file-value" in html


def test_file_upload_threads_accept_and_max_size_when_set() -> None:
    """`accept` and `max_size_bytes > 0` emit their respective data-attrs.
    Empty/zero values omit the attribute entirely (no empty `data-dz-accept=""`)."""
    html = FragmentRenderer().render(
        FileUpload(
            name="f",
            label="F",
            upload_url=URL("/u"),
            accept=".pdf,.doc",
            max_size_bytes=10485760,
        )
    )
    assert 'data-dz-accept=".pdf,.doc"' in html
    assert 'data-dz-max-size="10485760"' in html

    html_clean = FragmentRenderer().render(FileUpload(name="f", label="F", upload_url=URL("/u")))
    assert "data-dz-accept" not in html_clean
    assert "data-dz-max-size" not in html_clean


def test_file_upload_threads_initial_value_for_edit_mode() -> None:
    """EDIT-mode initial_value (the persisted file key/URL) reaches
    the hidden input's `value=` attribute."""
    html = FragmentRenderer().render(
        FileUpload(
            name="f",
            label="F",
            upload_url=URL("/u"),
            initial_value="docs/2026/abc-123.pdf",
        )
    )
    assert 'value="docs/2026/abc-123.pdf"' in html


def test_file_upload_threads_initial_label_data_attr() -> None:
    """`initial_label` (typically the original filename) emits as
    `data-dz-initial-label` so the Alpine widget can show "report.pdf"
    until the user picks a different file."""
    html = FragmentRenderer().render(
        FileUpload(
            name="f",
            label="F",
            upload_url=URL("/u"),
            initial_label="annual-report.pdf",
        )
    )
    assert 'data-dz-initial-label="annual-report.pdf"' in html


def test_file_upload_required_attribute() -> None:
    """`required=True` emits the `required` HTML attribute on the
    hidden input — form validation gates POST when no file is set."""
    html = FragmentRenderer().render(
        FileUpload(name="f", label="F", upload_url=URL("/u"), required=True)
    )
    assert "required" in html


def test_file_upload_escapes_label_and_attrs() -> None:
    """User-supplied label + initial_label escape attribute-context
    chars. Defensive against XSS via DSL author error or upstream
    field metadata."""
    html = FragmentRenderer().render(
        FileUpload(
            name="f",
            label="<script>",
            upload_url=URL("/u"),
            initial_label='"><script>alert(1)</script>',
        )
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ── Adapter dispatch ──


def test_field_to_primitive_dispatches_kind_file_to_file_upload() -> None:
    """`_field_to_primitive` returns FileUpload when `kind == "file"`
    — regardless of whether other dispatch keys (options, ref_api)
    are also present."""
    prim = _field_to_primitive({"name": "doc", "label": "Doc", "kind": "file", "value": ""})
    assert isinstance(prim, FileUpload)
    assert prim.name == "doc"
    assert prim.label == "Doc"


def test_field_to_primitive_threads_file_options_through() -> None:
    """All FileUpload-relevant ctx fields (`upload_url`, `accept`,
    `max_size_bytes`, `value`, `initial_label`, `required`) reach
    the primitive."""
    prim = _field_to_primitive(
        {
            "name": "doc",
            "label": "Doc",
            "kind": "file",
            "value": "key-abc",
            "required": True,
            "upload_url": "/uploads/documents",
            "accept": ".pdf,.docx",
            "max_size_bytes": 5242880,
            "initial_label": "old-name.pdf",
        }
    )
    assert isinstance(prim, FileUpload)
    assert str(prim.upload_url) == "/uploads/documents"
    assert prim.accept == ".pdf,.docx"
    assert prim.max_size_bytes == 5242880
    assert prim.initial_value == "key-abc"
    assert prim.initial_label == "old-name.pdf"
    assert prim.required is True


def test_field_to_primitive_file_kind_defaults_upload_url() -> None:
    """If `upload_url` is missing in the dispatch ctx (legacy path),
    fall back to the conventional `/uploads` — matches the legacy
    Jinja widget's default endpoint."""
    prim = _field_to_primitive({"name": "doc", "label": "Doc", "kind": "file", "value": ""})
    assert isinstance(prim, FileUpload)
    assert str(prim.upload_url) == "/uploads"


# ── Coverage audit ──


def test_unsupported_field_types_no_longer_includes_file() -> None:
    """Issue #1033 closure: the audit's blocker list drops `"file"` —
    cyfuture's fragment-audit should now report zero blockers."""
    assert "file" not in _UNSUPPORTED_FIELD_TYPES
