"""Tests for vendor mock state store."""

from __future__ import annotations

from dazzle.testing.vendor_mock.data_generators import DataGenerator
from dazzle.testing.vendor_mock.state import MockStateStore


def _sumsub_models() -> dict:
    """Minimal SumSub-like model definitions for testing."""
    return {
        "Applicant": {
            "description": "A person undergoing verification",
            "key": "id",
            "fields": {
                "id": {"type": "str(50)", "required": True, "pk": True},
                "external_user_id": {"type": "str(100)"},
                "type": {"type": "enum[individual,company]", "required": True},
                "email": {"type": "email"},
                "first_name": {"type": "str(100)"},
                "last_name": {"type": "str(100)"},
                "review_status": {"type": "enum[init,pending,completed]"},
                "created_at": {"type": "datetime"},
                "updated_at": {"type": "datetime"},
            },
        },
        "Document": {
            "description": "An identity document",
            "key": "id",
            "fields": {
                "id": {"type": "str(50)", "required": True, "pk": True},
                "applicant_id": {"type": "str(50)", "required": True},
                "id_doc_type": {"type": "enum[PASSPORT,ID_CARD,DRIVERS]", "required": True},
                "country": {"type": "str(3)", "required": True},
            },
        },
    }


def _int_pk_models() -> dict:
    """Model with integer PK for testing sequential IDs."""
    return {
        "Template": {
            "description": "A document template",
            "key": "id",
            "fields": {
                "id": {"type": "int", "required": True, "pk": True},
                "name": {"type": "str(200)", "required": True},
                "created_at": {"type": "datetime"},
            },
        },
    }


class TestCreate:
    def test_creates_with_auto_id(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        record = store.create("Applicant", {"type": "individual", "email": "test@example.com"})
        assert record["id"] is not None
        assert record["id"].startswith("App_") or record["id"].startswith("app_")

    def test_creates_with_provided_id(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        record = store.create("Applicant", {"id": "custom-123", "type": "individual"})
        assert record["id"] == "custom-123"

    def test_creates_with_int_pk(self) -> None:
        store = MockStateStore(foreign_models=_int_pk_models(), generator=DataGenerator(seed=1))
        r1 = store.create("Template", {"name": "Template A"})
        r2 = store.create("Template", {"name": "Template B"})
        assert r1["id"] == 1
        assert r2["id"] == 2

    def test_auto_sets_timestamps(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        record = store.create("Applicant", {"type": "individual"})
        assert record.get("created_at") is not None
        assert record.get("updated_at") is not None

    def test_preserves_provided_data(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        record = store.create(
            "Applicant",
            {"type": "company", "email": "corp@test.com", "first_name": "Test Corp"},
        )
        assert record["type"] == "company"
        assert record["email"] == "corp@test.com"
        assert record["first_name"] == "Test Corp"

    def test_generates_defaults_for_required_fields(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        record = store.create("Applicant", {})
        # 'type' is required — should have a generated value
        assert record["type"] in ("individual", "company")


class TestGet:
    def test_get_returns_created_record(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        created = store.create("Applicant", {"type": "individual", "email": "get@test.com"})
        fetched = store.get("Applicant", created["id"])
        assert fetched is not None
        assert fetched["email"] == "get@test.com"

    def test_get_returns_none_for_missing(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        assert store.get("Applicant", "nonexistent") is None

    def test_get_returns_none_for_unknown_model(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        assert store.get("UnknownModel", "any-id") is None


class TestList:
    def test_list_returns_all_records(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        store.create("Applicant", {"type": "individual"})
        store.create("Applicant", {"type": "company"})
        records = store.list("Applicant")
        assert len(records) == 2

    def test_list_empty_collection(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        assert store.list("Applicant") == []

    def test_list_with_filter(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        store.create("Applicant", {"type": "individual"})
        store.create("Applicant", {"type": "company"})
        store.create("Applicant", {"type": "individual"})
        individuals = store.list("Applicant", type="individual")
        assert len(individuals) == 2
        assert all(r["type"] == "individual" for r in individuals)


class TestUpdate:
    def test_update_modifies_record(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        created = store.create("Applicant", {"type": "individual", "review_status": "init"})
        updated = store.update("Applicant", created["id"], {"review_status": "pending"})
        assert updated is not None
        assert updated["review_status"] == "pending"
        # Original fields preserved
        assert updated["type"] == "individual"

    def test_update_sets_updated_at(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        created = store.create("Applicant", {"type": "individual"})
        updated = store.update("Applicant", created["id"], {"email": "new@test.com"})
        assert updated is not None
        # updated_at should change (or at least be set)
        assert updated.get("updated_at") is not None

    def test_update_returns_none_for_missing(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        assert store.update("Applicant", "nonexistent", {"type": "company"}) is None

    def test_update_persists(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        created = store.create("Applicant", {"type": "individual"})
        store.update("Applicant", created["id"], {"email": "persisted@test.com"})
        fetched = store.get("Applicant", created["id"])
        assert fetched is not None
        assert fetched["email"] == "persisted@test.com"


class TestDelete:
    def test_delete_removes_record(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        created = store.create("Applicant", {"type": "individual"})
        assert store.delete("Applicant", created["id"]) is True
        assert store.get("Applicant", created["id"]) is None

    def test_delete_returns_false_for_missing(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        assert store.delete("Applicant", "nonexistent") is False


class TestClear:
    def test_clear_all(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        store.create("Applicant", {"type": "individual"})
        store.create("Document", {"applicant_id": "x", "id_doc_type": "PASSPORT", "country": "GBR"})
        store.clear()
        assert store.list("Applicant") == []
        assert store.list("Document") == []

    def test_clear_specific_model(self) -> None:
        store = MockStateStore(foreign_models=_sumsub_models(), generator=DataGenerator(seed=1))
        store.create("Applicant", {"type": "individual"})
        store.create("Document", {"applicant_id": "x", "id_doc_type": "PASSPORT", "country": "GBR"})
        store.clear("Applicant")
        assert store.list("Applicant") == []
        assert len(store.list("Document")) == 1
