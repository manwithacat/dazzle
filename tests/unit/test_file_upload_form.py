"""
Unit tests for file upload form integration.

Tests that FILE field types are correctly mapped to form types,
field elements, and template filters.
"""

from __future__ import annotations

from dazzle.core import ir
from dazzle.core.ir import EntitySpec, FieldTypeKind
from dazzle.core.ir.fields import FieldSpec, FieldType
from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle_ui.converters.template_compiler import (
    _build_form_fields,
    _field_type_to_form_type,
    _file_accept_attr,
)
from dazzle_ui.runtime.template_renderer import _basename_or_url_filter


class TestFieldTypeToFormType:
    """Tests for _field_type_to_form_type with file fields."""

    def test_file_field_maps_to_file(self) -> None:
        spec = FieldSpec(
            name="document",
            type=FieldType(kind=FieldTypeKind.FILE),
        )
        assert _field_type_to_form_type(spec) == "file"

    def test_other_fields_unchanged(self) -> None:
        spec = FieldSpec(
            name="name",
            type=FieldType(kind=FieldTypeKind.STR),
        )
        assert _field_type_to_form_type(spec) == "text"

    def test_bool_field(self) -> None:
        spec = FieldSpec(
            name="active",
            type=FieldType(kind=FieldTypeKind.BOOL),
        )
        assert _field_type_to_form_type(spec) == "checkbox"

    def test_none_field(self) -> None:
        assert _field_type_to_form_type(None) == "text"


class TestFileAcceptAttr:
    """Tests for _file_accept_attr helper."""

    def test_default_accept(self) -> None:
        spec = FieldSpec(
            name="doc",
            type=FieldType(kind=FieldTypeKind.FILE),
        )
        assert _file_accept_attr(spec) == "*/*"

    def test_str_type_defaults(self) -> None:
        """Non-file field type still returns */* (graceful fallback)."""
        spec = FieldSpec(
            name="doc",
            type=FieldType(kind=FieldTypeKind.STR),
        )
        assert _file_accept_attr(spec) == "*/*"


class TestFileCaptureAttribute:
    """Tests for capture and accept options on FILE fields (#334)."""

    def _make_file_entity(self) -> EntitySpec:
        return EntitySpec(
            name="Document",
            fields=[
                FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True),
                FieldSpec(name="photo", type=FieldType(kind=FieldTypeKind.FILE)),
                FieldSpec(name="name", type=FieldType(kind=FieldTypeKind.STR)),
            ],
        )

    def test_capture_from_element_options(self) -> None:
        """Surface field with capture= option passes through to extra."""
        entity = self._make_file_entity()
        surface = SurfaceSpec(
            name="photo_upload",
            entity_ref="Document",
            mode=SurfaceMode.CREATE,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    elements=[
                        ir.SurfaceElement(
                            field_name="photo",
                            label="Take Photo",
                            options={"accept": "image/*", "capture": "environment"},
                        ),
                    ],
                ),
            ],
        )
        fields = _build_form_fields(surface, entity)
        photo_field = next(f for f in fields if f.name == "photo")
        assert photo_field.extra["capture"] == "environment"
        assert photo_field.extra["accept"] == "image/*"

    def test_accept_override_from_element_options(self) -> None:
        """Surface field with accept= option overrides default."""
        entity = self._make_file_entity()
        surface = SurfaceSpec(
            name="doc_upload",
            entity_ref="Document",
            mode=SurfaceMode.CREATE,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    elements=[
                        ir.SurfaceElement(
                            field_name="photo",
                            label="Document",
                            options={"accept": ".pdf,.doc"},
                        ),
                    ],
                ),
            ],
        )
        fields = _build_form_fields(surface, entity)
        photo_field = next(f for f in fields if f.name == "photo")
        assert photo_field.extra["accept"] == ".pdf,.doc"
        assert "capture" not in photo_field.extra

    def test_no_capture_when_not_specified(self) -> None:
        """FILE field without capture option has no capture in extra."""
        entity = self._make_file_entity()
        surface = SurfaceSpec(
            name="upload",
            entity_ref="Document",
            mode=SurfaceMode.CREATE,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    elements=[
                        ir.SurfaceElement(field_name="photo", label="Photo"),
                    ],
                ),
            ],
        )
        fields = _build_form_fields(surface, entity)
        photo_field = next(f for f in fields if f.name == "photo")
        assert photo_field.extra["accept"] == "*/*"
        assert "capture" not in photo_field.extra

    def test_user_camera_capture(self) -> None:
        """capture=user opens front camera."""
        entity = self._make_file_entity()
        surface = SurfaceSpec(
            name="selfie",
            entity_ref="Document",
            mode=SurfaceMode.CREATE,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    elements=[
                        ir.SurfaceElement(
                            field_name="photo",
                            label="Selfie",
                            options={"capture": "user"},
                        ),
                    ],
                ),
            ],
        )
        fields = _build_form_fields(surface, entity)
        photo_field = next(f for f in fields if f.name == "photo")
        assert photo_field.extra["capture"] == "user"


class TestBasenameOrUrlFilter:
    """Tests for the basename_or_url Jinja2 filter."""

    def test_url_extracts_filename(self) -> None:
        assert _basename_or_url_filter("/files/abc/photo.jpg") == "photo.jpg"

    def test_url_with_query_string(self) -> None:
        assert _basename_or_url_filter("/files/abc/doc.pdf?v=2") == "doc.pdf"

    def test_full_url(self) -> None:
        assert _basename_or_url_filter("https://example.com/uploads/file.txt") == "file.txt"

    def test_plain_filename(self) -> None:
        assert _basename_or_url_filter("report.xlsx") == "report.xlsx"

    def test_none_value(self) -> None:
        assert _basename_or_url_filter(None) == ""

    def test_empty_string(self) -> None:
        assert _basename_or_url_filter("") == ""

    def test_trailing_slash(self) -> None:
        # Edge case: URL ending in /
        result = _basename_or_url_filter("/files/uploads/")
        # Should return the full URL since basename is empty
        assert result == "/files/uploads/"
