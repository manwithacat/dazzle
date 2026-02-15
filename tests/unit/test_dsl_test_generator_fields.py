"""Tests for field value generation fixes (#246–#252)."""

from __future__ import annotations

from dazzle.core.ir import AppSpec
from dazzle.core.ir.domain import DomainSpec, EntitySpec
from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.testing.dsl_test_generator import DSLTestGenerator


def _pk_field() -> FieldSpec:
    return FieldSpec(
        name="id",
        type=FieldType(kind=FieldTypeKind.UUID),
        modifiers=[FieldModifier.PK],
    )


def _str_field(
    name: str, required: bool = True, unique: bool = False, max_length: int = 200
) -> FieldSpec:
    mods = []
    if required:
        mods.append(FieldModifier.REQUIRED)
    if unique:
        mods.append(FieldModifier.UNIQUE)
    return FieldSpec(
        name=name,
        type=FieldType(kind=FieldTypeKind.STR, max_length=max_length),
        modifiers=mods,
    )


def _money_field(name: str, currency: str = "GBP", required: bool = True) -> FieldSpec:
    mods = [FieldModifier.REQUIRED] if required else []
    return FieldSpec(
        name=name,
        type=FieldType(kind=FieldTypeKind.MONEY, currency_code=currency),
        modifiers=mods,
    )


def _make_appspec(*entities: EntitySpec) -> AppSpec:
    # Auto-create create surfaces so CRUD CREATE tests are generated
    surfaces = [
        SurfaceSpec(name=f"{e.name.lower()}_create", entity_ref=e.name, mode=SurfaceMode.CREATE)
        for e in entities
    ]
    return AppSpec(
        name="test",
        title="Test",
        domain=DomainSpec(entities=list(entities)),
        surfaces=surfaces,
        views=[],
        enums=[],
        processes=[],
        ledgers=[],
        transactions=[],
        workspaces=[],
        experiences=[],
        personas=[],
        stories=[],
        webhooks=[],
        approvals=[],
        slas=[],
        islands=[],
    )


# ---------------------------------------------------------------------------
# #246: Money field flattening
# ---------------------------------------------------------------------------


class TestMoneyFieldFlattening:
    """Money fields should produce {name}_minor and {name}_currency keys."""

    def test_entity_data_has_flat_money_keys(self):
        entity = EntitySpec(
            name="Package",
            title="Package",
            fields=[_pk_field(), _str_field("name"), _money_field("monthly_fee", "GBP")],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data = gen._generate_entity_data(entity)
        assert "monthly_fee_minor" in data
        assert "monthly_fee_currency" in data
        assert data["monthly_fee_minor"] == 10000
        assert data["monthly_fee_currency"] == "GBP"

    def test_entity_data_no_nested_money(self):
        entity = EntitySpec(
            name="Package",
            title="Package",
            fields=[_pk_field(), _str_field("name"), _money_field("monthly_fee")],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data = gen._generate_entity_data(entity)
        # Should NOT have the nested format
        assert "monthly_fee" not in data

    def test_money_uses_field_currency(self):
        entity = EntitySpec(
            name="Invoice",
            title="Invoice",
            fields=[_pk_field(), _str_field("title"), _money_field("amount", "EUR")],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data = gen._generate_entity_data(entity)
        assert data["amount_currency"] == "EUR"

    def test_money_defaults_to_usd(self):
        entity = EntitySpec(
            name="Invoice",
            title="Invoice",
            fields=[
                _pk_field(),
                _str_field("title"),
                FieldSpec(
                    name="total",
                    type=FieldType(kind=FieldTypeKind.MONEY),
                    modifiers=[FieldModifier.REQUIRED],
                ),
            ],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data = gen._generate_entity_data(entity)
        assert data["total_currency"] == "USD"

    def test_crud_test_data_uses_flat_money(self):
        """End-to-end: CRUD create test step uses flat money keys."""
        entity = EntitySpec(
            name="Package",
            title="Package",
            fields=[_pk_field(), _str_field("name"), _money_field("price", "GBP")],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        suite = gen.generate_all()
        create_test = next(d for d in suite.designs if d["test_id"] == "CRUD_PACKAGE_CREATE")
        create_step = next(s for s in create_test["steps"] if s["action"] == "create")
        assert "price_minor" in create_step["data"]
        assert "price_currency" in create_step["data"]
        assert "price" not in create_step["data"]

    def test_multiple_money_fields(self):
        entity = EntitySpec(
            name="Invoice",
            title="Invoice",
            fields=[
                _pk_field(),
                _str_field("title"),
                _money_field("subtotal", "GBP"),
                _money_field("tax", "GBP"),
            ],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data = gen._generate_entity_data(entity)
        assert data["subtotal_minor"] == 10000
        assert data["subtotal_currency"] == "GBP"
        assert data["tax_minor"] == 10000
        assert data["tax_currency"] == "GBP"


# ---------------------------------------------------------------------------
# #247: Unique field randomness
# ---------------------------------------------------------------------------


class TestUniqueFieldRandomness:
    """Unique fields should produce random values that differ across calls."""

    def test_unique_str_has_random_suffix(self):
        entity = EntitySpec(
            name="Company",
            title="Company",
            fields=[_pk_field(), _str_field("company_number", unique=True)],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data1 = gen._generate_entity_data(entity)
        data2 = gen._generate_entity_data(entity)
        assert data1["company_number"] != data2["company_number"]

    def test_unique_str_respects_max_length(self):
        entity = EntitySpec(
            name="Code",
            title="Code",
            fields=[_pk_field(), _str_field("code", unique=True, max_length=15)],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data = gen._generate_entity_data(entity)
        assert len(data["code"]) <= 15

    def test_non_unique_str_is_deterministic(self):
        entity = EntitySpec(
            name="Task",
            title="Task",
            fields=[_pk_field(), _str_field("title", unique=False)],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data1 = gen._generate_entity_data(entity)
        data2 = gen._generate_entity_data(entity)
        assert data1["title"] == data2["title"]

    def test_unique_email_has_random_suffix(self):
        entity = EntitySpec(
            name="User",
            title="User",
            fields=[
                _pk_field(),
                FieldSpec(
                    name="email",
                    type=FieldType(kind=FieldTypeKind.EMAIL),
                    modifiers=[FieldModifier.REQUIRED, FieldModifier.UNIQUE],
                ),
            ],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data1 = gen._generate_entity_data(entity)
        data2 = gen._generate_entity_data(entity)
        assert data1["email"] != data2["email"]
        assert data1["email"].endswith("@example.com")

    def test_unique_url_has_random_suffix(self):
        entity = EntitySpec(
            name="Bookmark",
            title="Bookmark",
            fields=[
                _pk_field(),
                FieldSpec(
                    name="link",
                    type=FieldType(kind=FieldTypeKind.URL),
                    modifiers=[FieldModifier.REQUIRED, FieldModifier.UNIQUE],
                ),
            ],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data1 = gen._generate_entity_data(entity)
        data2 = gen._generate_entity_data(entity)
        assert data1["link"] != data2["link"]
        assert data1["link"].startswith("https://example.com/")

    def test_two_generators_produce_different_values(self):
        """Even across separate generator instances, unique fields differ."""
        entity = EntitySpec(
            name="Company",
            title="Company",
            fields=[_pk_field(), _str_field("slug", unique=True)],
        )
        appspec = _make_appspec(entity)
        gen1 = DSLTestGenerator(appspec)
        gen2 = DSLTestGenerator(appspec)
        data1 = gen1._generate_entity_data(entity)
        data2 = gen2._generate_entity_data(entity)
        assert data1["slug"] != data2["slug"]


# ---------------------------------------------------------------------------
# #251: Per-test fresh data avoids unique collisions
# ---------------------------------------------------------------------------


class TestPerTestFreshData:
    """CREATE and READ tests should have different unique field values."""

    def test_create_and_read_have_different_data(self):
        entity = EntitySpec(
            name="Company",
            title="Company",
            fields=[_pk_field(), _str_field("slug", unique=True), _str_field("name")],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        suite = gen.generate_all()
        create_test = next(d for d in suite.designs if d["test_id"] == "CRUD_COMPANY_CREATE")
        read_test = next(d for d in suite.designs if d["test_id"] == "CRUD_COMPANY_READ")
        create_step = next(s for s in create_test["steps"] if s["action"] == "create")
        read_step = next(s for s in read_test["steps"] if s["action"] == "create")
        # Unique field should differ between CREATE and READ tests
        assert create_step["data"]["slug"] != read_step["data"]["slug"]

    def test_unique_test_uses_same_data_twice(self):
        """VAL_UNIQUE test should use the SAME data for both create attempts."""
        entity = EntitySpec(
            name="Company",
            title="Company",
            fields=[_pk_field(), _str_field("slug", unique=True), _str_field("name")],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        suite = gen.generate_all()
        unique_test = next(d for d in suite.designs if d["test_id"] == "VAL_COMPANY_SLUG_UNIQUE")
        create_steps = [
            s for s in unique_test["steps"] if s["action"] in ("create", "create_expect_error")
        ]
        assert len(create_steps) == 2
        assert create_steps[0]["data"] == create_steps[1]["data"]

    def test_unique_test_data_differs_from_create(self):
        """VAL_UNIQUE test data should differ from CRUD_CREATE data."""
        entity = EntitySpec(
            name="Company",
            title="Company",
            fields=[_pk_field(), _str_field("slug", unique=True), _str_field("name")],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        suite = gen.generate_all()
        create_test = next(d for d in suite.designs if d["test_id"] == "CRUD_COMPANY_CREATE")
        unique_test = next(d for d in suite.designs if d["test_id"] == "VAL_COMPANY_SLUG_UNIQUE")
        create_slug = next(s for s in create_test["steps"] if s["action"] == "create")["data"][
            "slug"
        ]
        unique_slug = next(s for s in unique_test["steps"] if s["action"] == "create")["data"][
            "slug"
        ]
        assert create_slug != unique_slug

    def test_non_unique_fields_are_consistent(self):
        """Non-unique fields can be the same across tests (they're deterministic)."""
        entity = EntitySpec(
            name="Task",
            title="Task",
            fields=[_pk_field(), _str_field("title", unique=False)],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        suite = gen.generate_all()
        create_test = next(d for d in suite.designs if d["test_id"] == "CRUD_TASK_CREATE")
        read_test = next(d for d in suite.designs if d["test_id"] == "CRUD_TASK_READ")
        create_title = next(s for s in create_test["steps"] if s["action"] == "create")["data"][
            "title"
        ]
        read_title = next(s for s in read_test["steps"] if s["action"] == "create")["data"]["title"]
        assert create_title == read_title


# ---------------------------------------------------------------------------
# #252: Short max_length unique fields use hex-only values
# ---------------------------------------------------------------------------


class TestShortUniqueFields:
    """Unique fields with short max_length should use hex-only values."""

    def test_short_unique_uses_hex(self):
        entity = EntitySpec(
            name="Company",
            title="Company",
            fields=[_pk_field(), _str_field("code", unique=True, max_length=8)],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data = gen._generate_entity_data(entity)
        assert len(data["code"]) == 8
        # Should be valid hex
        int(data["code"], 16)

    def test_short_unique_respects_max_length(self):
        entity = EntitySpec(
            name="Company",
            title="Company",
            fields=[_pk_field(), _str_field("code", unique=True, max_length=6)],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data = gen._generate_entity_data(entity)
        assert len(data["code"]) == 6

    def test_short_unique_is_random(self):
        entity = EntitySpec(
            name="Company",
            title="Company",
            fields=[_pk_field(), _str_field("code", unique=True, max_length=8)],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data1 = gen._generate_entity_data(entity)
        data2 = gen._generate_entity_data(entity)
        assert data1["code"] != data2["code"]

    def test_boundary_16_uses_hex(self):
        """max_length=16 should still use hex (boundary case)."""
        entity = EntitySpec(
            name="Item",
            title="Item",
            fields=[_pk_field(), _str_field("sku", unique=True, max_length=16)],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data = gen._generate_entity_data(entity)
        assert len(data["sku"]) == 16
        int(data["sku"], 16)

    def test_boundary_17_uses_normal(self):
        """max_length=17 should use normal Test prefix (just above threshold)."""
        entity = EntitySpec(
            name="Item",
            title="Item",
            fields=[_pk_field(), _str_field("sku", unique=True, max_length=17)],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data = gen._generate_entity_data(entity)
        assert data["sku"].startswith("Test")

    def test_non_unique_short_not_hex(self):
        """Non-unique short fields should NOT use hex (deterministic is fine)."""
        entity = EntitySpec(
            name="Company",
            title="Company",
            fields=[_pk_field(), _str_field("code", unique=False, max_length=8)],
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        data = gen._generate_entity_data(entity)
        assert data["code"].startswith("Test")
