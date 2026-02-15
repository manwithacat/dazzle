"""Tests for build_entity_list_projections() — money field expansion and view projections."""

from __future__ import annotations

import dazzle.core.ir as ir
from dazzle_back.runtime.server import build_entity_list_projections


def _entity(name: str, fields: list[ir.FieldSpec]) -> ir.EntitySpec:
    return ir.EntitySpec(name=name, title=name, fields=fields)


def _field(name: str, kind: ir.FieldTypeKind, required: bool = False) -> ir.FieldSpec:
    modifiers = [ir.FieldModifier.REQUIRED] if required else []
    return ir.FieldSpec(name=name, type=ir.FieldType(kind=kind), modifiers=modifiers)


def _pk(name: str = "id") -> ir.FieldSpec:
    return ir.FieldSpec(
        name=name,
        type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
        modifiers=[ir.FieldModifier.PK],
    )


def _surface(name: str, entity_ref: str, view_ref: str) -> ir.SurfaceSpec:
    return ir.SurfaceSpec(
        name=name, entity_ref=entity_ref, view_ref=view_ref, mode=ir.SurfaceMode.LIST
    )


def _view(name: str, field_names: list[str]) -> ir.ViewSpec:
    return ir.ViewSpec(
        name=name,
        fields=[ir.ViewFieldSpec(name=n) for n in field_names],
    )


# ── Money field expansion ────────────────────────────────────────────


class TestMoneyFieldExpansion:
    def test_money_field_expands_to_minor_and_currency(self) -> None:
        entity = _entity(
            "Invoice",
            [
                _pk(),
                _field("amount", ir.FieldTypeKind.MONEY),
                _field("status", ir.FieldTypeKind.STR),
            ],
        )
        surface = _surface("invoice_list", "Invoice", "invoice_view")
        view = _view("invoice_view", ["status", "amount"])

        result = build_entity_list_projections([entity], [surface], [view])

        assert result["Invoice"] == ["id", "status", "amount_minor", "amount_currency"]

    def test_multiple_money_fields_all_expand(self) -> None:
        entity = _entity(
            "VATReturn",
            [
                _pk(),
                _field("net_profit", ir.FieldTypeKind.MONEY),
                _field("vat_owed", ir.FieldTypeKind.MONEY),
                _field("period", ir.FieldTypeKind.STR),
            ],
        )
        surface = _surface("vat_list", "VATReturn", "vat_view")
        view = _view("vat_view", ["period", "net_profit", "vat_owed"])

        result = build_entity_list_projections([entity], [surface], [view])

        assert result["VATReturn"] == [
            "id",
            "period",
            "net_profit_minor",
            "net_profit_currency",
            "vat_owed_minor",
            "vat_owed_currency",
        ]

    def test_non_money_fields_pass_through_unchanged(self) -> None:
        entity = _entity(
            "Task",
            [_pk(), _field("title", ir.FieldTypeKind.STR), _field("done", ir.FieldTypeKind.BOOL)],
        )
        surface = _surface("task_list", "Task", "task_view")
        view = _view("task_view", ["title", "done"])

        result = build_entity_list_projections([entity], [surface], [view])

        assert result["Task"] == ["id", "title", "done"]


# ── ID injection ─────────────────────────────────────────────────────


class TestIdInjection:
    def test_id_prepended_when_missing_from_view(self) -> None:
        entity = _entity("Item", [_pk(), _field("name", ir.FieldTypeKind.STR)])
        surface = _surface("item_list", "Item", "item_view")
        view = _view("item_view", ["name"])

        result = build_entity_list_projections([entity], [surface], [view])

        assert result["Item"][0] == "id"

    def test_id_not_duplicated_when_in_view(self) -> None:
        entity = _entity("Item", [_pk(), _field("name", ir.FieldTypeKind.STR)])
        surface = _surface("item_list", "Item", "item_view")
        view = _view("item_view", ["id", "name"])

        result = build_entity_list_projections([entity], [surface], [view])

        assert result["Item"].count("id") == 1


# ── Required field inclusion ─────────────────────────────────────────


class TestRequiredFieldInclusion:
    def test_required_field_not_in_view_is_included(self) -> None:
        entity = _entity(
            "Order",
            [
                _pk(),
                _field("title", ir.FieldTypeKind.STR, required=True),
                _field("notes", ir.FieldTypeKind.TEXT),
            ],
        )
        surface = _surface("order_list", "Order", "order_view")
        view = _view("order_view", ["notes"])

        result = build_entity_list_projections([entity], [surface], [view])

        # title is required but not in view — must be included
        assert "title" in result["Order"]
        assert "notes" in result["Order"]

    def test_required_money_field_not_in_view_expands(self) -> None:
        entity = _entity(
            "Invoice",
            [
                _pk(),
                _field("amount", ir.FieldTypeKind.MONEY, required=True),
                _field("status", ir.FieldTypeKind.STR),
            ],
        )
        surface = _surface("inv_list", "Invoice", "inv_view")
        view = _view("inv_view", ["status"])

        result = build_entity_list_projections([entity], [surface], [view])

        # amount is required + money → both storage columns must appear
        assert "amount_minor" in result["Invoice"]
        assert "amount_currency" in result["Invoice"]


# ── Edge cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    def test_surface_without_view_ref_ignored(self) -> None:
        entity = _entity("Task", [_pk(), _field("title", ir.FieldTypeKind.STR)])
        surface = ir.SurfaceSpec(
            name="task_list", entity_ref="Task", view_ref=None, mode=ir.SurfaceMode.LIST
        )

        result = build_entity_list_projections([entity], [surface], [])

        assert result == {}

    def test_surface_with_missing_view_ignored(self) -> None:
        entity = _entity("Task", [_pk(), _field("title", ir.FieldTypeKind.STR)])
        surface = _surface("task_list", "Task", "nonexistent_view")

        result = build_entity_list_projections([entity], [surface], [])

        assert result == {}

    def test_empty_inputs(self) -> None:
        assert build_entity_list_projections([], [], []) == {}

    def test_view_with_empty_fields(self) -> None:
        entity = _entity("Task", [_pk(), _field("title", ir.FieldTypeKind.STR)])
        surface = _surface("task_list", "Task", "task_view")
        view = ir.ViewSpec(name="task_view", fields=[])

        result = build_entity_list_projections([entity], [surface], [view])

        assert result == {}
