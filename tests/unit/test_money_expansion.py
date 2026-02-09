"""
Tests for money(GBP) field expansion (Issue #131).

Tests cover:
- Entity converter: money field -> _minor (INT) + _currency (STR) expansion
- Surface converter: money field schema expansion in input schemas
- Template compiler: column key and form field expansion
- Template renderer: currency filter with minor units
- Mock data: expanded field generation
- Integration: DSL -> entity converter round-trip
"""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import (
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    SurfaceElement,
    SurfaceMode,
    SurfaceSection,
    SurfaceSpec,
)
from dazzle_back.converters.entity_converter import (
    _expand_money_field,
    convert_entity,
)
from dazzle_back.converters.surface_converter import (
    _generate_input_schema,
    _map_field_type_name,
)
from dazzle_back.specs import ScalarType
from dazzle_ui.converters.template_compiler import (
    _build_columns,
    _build_form_fields,
)
from dazzle_ui.runtime.mock_data import generate_mock_records
from dazzle_ui.runtime.template_renderer import _currency_filter

# =============================================================================
# Entity Converter Tests
# =============================================================================


class TestExpandMoneyField:
    """Test _expand_money_field() helper."""

    def _make_money_field(
        self,
        name: str = "monthly_fee",
        currency: str = "GBP",
        required: bool = True,
    ) -> FieldSpec:
        modifiers = [FieldModifier.REQUIRED] if required else []
        return FieldSpec(
            name=name,
            type=FieldType(kind=FieldTypeKind.MONEY, currency_code=currency),
            modifiers=modifiers,
        )

    def test_expands_to_two_fields(self):
        """Money field produces exactly two BackendSpec fields."""
        result = _expand_money_field(self._make_money_field())
        assert len(result) == 2

    def test_minor_field_name(self):
        """First field is {name}_minor."""
        result = _expand_money_field(self._make_money_field())
        assert result[0].name == "monthly_fee_minor"

    def test_currency_field_name(self):
        """Second field is {name}_currency."""
        result = _expand_money_field(self._make_money_field())
        assert result[1].name == "monthly_fee_currency"

    def test_minor_field_is_int(self):
        """_minor field is scalar INT."""
        result = _expand_money_field(self._make_money_field())
        assert result[0].type.kind == "scalar"
        assert result[0].type.scalar_type == ScalarType.INT

    def test_currency_field_is_str(self):
        """_currency field is scalar STR with max_length=3."""
        result = _expand_money_field(self._make_money_field())
        assert result[1].type.kind == "scalar"
        assert result[1].type.scalar_type == ScalarType.STR
        assert result[1].type.max_length == 3

    def test_currency_default_gbp(self):
        """_currency field defaults to GBP."""
        result = _expand_money_field(self._make_money_field(currency="GBP"))
        assert result[1].default == "GBP"

    def test_currency_default_usd(self):
        """_currency field uses the currency from DSL."""
        result = _expand_money_field(self._make_money_field(currency="USD"))
        assert result[1].default == "USD"

    def test_minor_preserves_required(self):
        """_minor field inherits required from original."""
        result = _expand_money_field(self._make_money_field(required=True))
        assert result[0].required is True

    def test_minor_not_required_when_original_not(self):
        result = _expand_money_field(self._make_money_field(required=False))
        assert result[0].required is False

    def test_currency_never_required(self):
        """_currency field is never required (has default)."""
        result = _expand_money_field(self._make_money_field(required=True))
        assert result[1].required is False


class TestConvertEntityWithMoney:
    """Test convert_entity() expands money fields."""

    def _make_entity_with_money(self, currency: str = "GBP") -> EntitySpec:
        return EntitySpec(
            name="Plan",
            title="Plan",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="name",
                    type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                    modifiers=[FieldModifier.REQUIRED],
                ),
                FieldSpec(
                    name="monthly_fee",
                    type=FieldType(kind=FieldTypeKind.MONEY, currency_code=currency),
                    modifiers=[FieldModifier.REQUIRED],
                ),
            ],
        )

    def test_entity_has_expanded_fields(self):
        """Converted entity has _minor and _currency instead of original money field."""
        result = convert_entity(self._make_entity_with_money())
        field_names = [f.name for f in result.fields]
        assert "monthly_fee_minor" in field_names
        assert "monthly_fee_currency" in field_names
        assert "monthly_fee" not in field_names

    def test_entity_field_count(self):
        """3 IR fields (id, name, money) -> 4 BackendSpec fields (id, name, _minor, _currency)."""
        result = convert_entity(self._make_entity_with_money())
        assert len(result.fields) == 4

    def test_non_money_fields_unchanged(self):
        """Non-money fields convert normally."""
        result = convert_entity(self._make_entity_with_money())
        name_field = next(f for f in result.fields if f.name == "name")
        assert name_field.type.kind == "scalar"
        assert name_field.type.scalar_type == ScalarType.STR


# =============================================================================
# Surface Converter Tests
# =============================================================================


class TestSurfaceConverterMoney:
    """Test surface converter handles money field expansion."""

    def test_map_field_type_name_money(self):
        """money maps to 'int' (minor units)."""
        ft = FieldType(kind=FieldTypeKind.MONEY, currency_code="GBP")
        assert _map_field_type_name(ft) == "int"

    def test_input_schema_expands_money(self):
        """Create/Edit surfaces expand money fields to _minor + _currency."""
        entity = EntitySpec(
            name="Plan",
            title="Plan",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="price",
                    type=FieldType(kind=FieldTypeKind.MONEY, currency_code="USD"),
                    modifiers=[FieldModifier.REQUIRED],
                ),
            ],
        )
        surface = SurfaceSpec(
            name="create_plan",
            title="Create Plan",
            entity_ref="Plan",
            mode=SurfaceMode.CREATE,
            sections=[
                SurfaceSection(
                    name="main",
                    elements=[SurfaceElement(field_name="price")],
                )
            ],
        )
        schema = _generate_input_schema(surface, entity)
        field_names = [f.name for f in schema.fields]
        assert "price_minor" in field_names
        assert "price_currency" in field_names
        assert "price" not in field_names

    def test_input_schema_minor_type_is_int(self):
        """_minor schema field is typed as int."""
        entity = EntitySpec(
            name="Plan",
            title="Plan",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="price",
                    type=FieldType(kind=FieldTypeKind.MONEY, currency_code="GBP"),
                    modifiers=[FieldModifier.REQUIRED],
                ),
            ],
        )
        surface = SurfaceSpec(
            name="create_plan",
            title="Create Plan",
            entity_ref="Plan",
            mode=SurfaceMode.CREATE,
            sections=[
                SurfaceSection(
                    name="main",
                    elements=[SurfaceElement(field_name="price")],
                )
            ],
        )
        schema = _generate_input_schema(surface, entity)
        minor_field = next(f for f in schema.fields if f.name == "price_minor")
        assert minor_field.type == "int"


# =============================================================================
# Template Compiler Tests
# =============================================================================


class TestTemplateCompilerMoney:
    """Test template compiler handles money field as single widget."""

    def _make_money_entity(self, currency_code: str = "GBP") -> EntitySpec:
        return EntitySpec(
            name="Invoice",
            title="Invoice",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="amount",
                    type=FieldType(kind=FieldTypeKind.MONEY, currency_code=currency_code),
                    modifiers=[FieldModifier.REQUIRED],
                ),
            ],
        )

    def _make_surface(self, mode: SurfaceMode = SurfaceMode.LIST) -> SurfaceSpec:
        return SurfaceSpec(
            name="invoice_list",
            title="Invoices",
            entity_ref="Invoice",
            mode=mode,
            sections=[
                SurfaceSection(
                    name="main",
                    elements=[SurfaceElement(field_name="amount", label="Amount")],
                )
            ],
        )

    def test_column_key_is_minor(self):
        """Table column key for money field is {name}_minor."""
        entity = self._make_money_entity()
        surface = self._make_surface(SurfaceMode.LIST)
        columns = _build_columns(surface, entity)
        amount_col = next(c for c in columns if c.label == "Amount")
        assert amount_col.key == "amount_minor"

    def test_column_type_is_currency(self):
        """Table column type for money field is 'currency'."""
        entity = self._make_money_entity()
        surface = self._make_surface(SurfaceMode.LIST)
        columns = _build_columns(surface, entity)
        amount_col = next(c for c in columns if c.label == "Amount")
        assert amount_col.type == "currency"

    def test_column_has_currency_code(self):
        """Table column carries currency_code for the currency filter."""
        entity = self._make_money_entity("USD")
        surface = self._make_surface(SurfaceMode.LIST)
        columns = _build_columns(surface, entity)
        amount_col = next(c for c in columns if c.label == "Amount")
        assert amount_col.currency_code == "USD"

    def test_form_fields_emit_single_money_field(self):
        """Form emits a single field with type='money' (not two fields)."""
        entity = self._make_money_entity()
        surface = self._make_surface(SurfaceMode.CREATE)
        fields = _build_form_fields(surface, entity)
        assert len(fields) == 1
        assert fields[0].name == "amount"
        assert fields[0].type == "money"

    def test_money_field_metadata(self):
        """Money field extra dict contains currency metadata."""
        entity = self._make_money_entity("GBP")
        surface = self._make_surface(SurfaceMode.CREATE)
        fields = _build_form_fields(surface, entity)
        field = fields[0]
        assert field.extra["currency_code"] == "GBP"
        assert field.extra["currency_fixed"] is True
        assert field.extra["scale"] == 2
        assert field.extra["symbol"] == "\u00a3"
        assert field.extra["currency_options"] == []

    def test_unpinned_money_has_currency_options(self):
        """Plain money type (no currency_code) gets dropdown options."""
        entity = EntitySpec(
            name="Invoice",
            title="Invoice",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="amount",
                    type=FieldType(kind=FieldTypeKind.MONEY, currency_code=""),
                    modifiers=[FieldModifier.REQUIRED],
                ),
            ],
        )
        surface = self._make_surface(SurfaceMode.CREATE)
        fields = _build_form_fields(surface, entity)
        field = fields[0]
        assert field.extra["currency_fixed"] is False
        assert len(field.extra["currency_options"]) > 0
        codes = [opt["code"] for opt in field.extra["currency_options"]]
        assert "GBP" in codes
        assert "USD" in codes


# =============================================================================
# Currency Filter Tests
# =============================================================================


class TestCurrencyFilter:
    """Test _currency_filter with ISO 4217 scale support."""

    def test_minor_units_default(self):
        """By default, minor=True divides by correct scale (100 for GBP)."""
        result = _currency_filter(2900, "GBP", minor=True)
        assert result == "\u00a329.00"

    def test_minor_false(self):
        """minor=False passes value through directly."""
        result = _currency_filter(29.0, "GBP", minor=False)
        assert result == "\u00a329.00"

    def test_usd_symbol(self):
        result = _currency_filter(1500, "USD", minor=True)
        assert result == "$15.00"

    def test_eur_symbol(self):
        result = _currency_filter(999, "EUR", minor=True)
        assert result == "\u20ac9.99"

    def test_none_value(self):
        assert _currency_filter(None) == ""

    def test_zero_value(self):
        result = _currency_filter(0, "GBP", minor=True)
        assert result == "\u00a30.00"

    def test_jpy_zero_decimal(self):
        """JPY has scale=0, so 1000 minor units = ¥1,000."""
        result = _currency_filter(1000, "JPY", minor=True)
        assert result == "\u00a51,000"

    def test_bhd_three_decimal(self):
        """BHD has scale=3, so 1999 minor units = BHD 1.999."""
        result = _currency_filter(1999, "BHD", minor=True)
        assert result == "BHD 1.999"


# =============================================================================
# Mock Data Tests
# =============================================================================


class TestMockDataMoney:
    """Test mock data generator handles money field expansion."""

    def test_generates_minor_and_currency_keys(self):
        """Mock records have _minor and _currency keys, not the original money field name."""
        entity = EntitySpec(
            name="Plan",
            title="Plan",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="price",
                    type=FieldType(kind=FieldTypeKind.MONEY, currency_code="EUR"),
                    modifiers=[FieldModifier.REQUIRED],
                ),
            ],
        )
        records = generate_mock_records(entity, count=3)
        for record in records:
            assert "price_minor" in record
            assert "price_currency" in record
            assert "price" not in record

    def test_minor_is_int(self):
        entity = EntitySpec(
            name="Plan",
            title="Plan",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="price",
                    type=FieldType(kind=FieldTypeKind.MONEY, currency_code="GBP"),
                ),
            ],
        )
        records = generate_mock_records(entity, count=1)
        assert isinstance(records[0]["price_minor"], int)

    def test_currency_from_field(self):
        entity = EntitySpec(
            name="Plan",
            title="Plan",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="price",
                    type=FieldType(kind=FieldTypeKind.MONEY, currency_code="USD"),
                ),
            ],
        )
        records = generate_mock_records(entity, count=1)
        assert records[0]["price_currency"] == "USD"


# =============================================================================
# Integration Test: DSL -> Entity Converter Round-Trip
# =============================================================================


class TestMoneyDSLIntegration:
    """Integration test: parse DSL with money field, convert, verify."""

    DSL_SOURCE = """\
module test_money
app money_test "Money Test"

entity Plan "Plan":
  id: uuid pk
  name: str(100) required
  monthly_fee: money(GBP) required

surface plan_list "Plans":
  uses entity Plan
  mode: list
  section main:
    field name "Name"
    field monthly_fee "Monthly Fee"
"""

    def test_parse_and_convert_entity(self):
        """DSL money field parses and converts to _minor/_currency BackendSpec fields."""
        _, _, _, _, _, fragment = parse_dsl(self.DSL_SOURCE, Path("test.dsl"))
        plan_entity = fragment.entities[0]
        assert plan_entity.name == "Plan"

        # Verify IR has MONEY kind
        fee_field = plan_entity.get_field("monthly_fee")
        assert fee_field is not None
        assert fee_field.type.kind == FieldTypeKind.MONEY
        assert fee_field.type.currency_code == "GBP"

        # Convert and verify expansion
        backend_entity = convert_entity(plan_entity)
        field_names = [f.name for f in backend_entity.fields]
        assert "monthly_fee_minor" in field_names
        assert "monthly_fee_currency" in field_names
        assert "monthly_fee" not in field_names

        # Verify types
        minor = next(f for f in backend_entity.fields if f.name == "monthly_fee_minor")
        assert minor.type.scalar_type == ScalarType.INT
        assert minor.required is True

        currency = next(f for f in backend_entity.fields if f.name == "monthly_fee_currency")
        assert currency.type.scalar_type == ScalarType.STR
        assert currency.default == "GBP"
