"""Tests for `ServiceFactory` entity-name lookups (#1181).

`ServiceFactory._services` is keyed by *service* name (`list_invoices`,
`read_invoices`, ...), not entity name. Code that did
`_services.get(entity_name)` therefore silently resolved to None. The
`services_by_entity()` / `service_for_entity()` accessors close that gap.
"""

from pydantic import BaseModel

from dazzle.http.runtime.service_generator import CRUDService, ServiceFactory
from dazzle.http.specs.service import DomainOperation, OperationKind, ServiceSpec


class _Invoice(BaseModel):
    id: str
    amount: int


class _Customer(BaseModel):
    id: str
    name: str


def _crud_spec(name: str, op: OperationKind, entity: str) -> ServiceSpec:
    return ServiceSpec(
        name=name,
        domain_operation=DomainOperation(kind=op, entity=entity),
    )


def _factory_with_two_entities() -> ServiceFactory:
    factory = ServiceFactory({"Invoice": _Invoice, "Customer": _Customer})
    factory.create_all_services(
        [
            _crud_spec("list_invoices", OperationKind.LIST, "Invoice"),
            _crud_spec("read_invoices", OperationKind.READ, "Invoice"),
            _crud_spec("list_customers", OperationKind.LIST, "Customer"),
        ]
    )
    return factory


def test_services_dict_is_keyed_by_service_name() -> None:
    """Confirms the keying that motivates the bug — `_services.get(entity)` misses."""
    factory = _factory_with_two_entities()
    assert set(factory._services) == {"list_invoices", "read_invoices", "list_customers"}
    # An entity-name lookup against the service-name-keyed dict silently misses.
    assert factory.get_service("Invoice") is None


def test_service_for_entity_resolves_by_entity_name() -> None:
    factory = _factory_with_two_entities()
    service = factory.service_for_entity("Invoice")
    assert isinstance(service, CRUDService)
    assert service.entity_name == "Invoice"


def test_service_for_entity_returns_none_for_unknown_entity() -> None:
    factory = _factory_with_two_entities()
    assert factory.service_for_entity("Nonexistent") is None


def test_services_by_entity_covers_every_entity_once() -> None:
    """Multiple CRUDServices per entity collapse to one entry — last wins."""
    factory = _factory_with_two_entities()
    by_entity = factory.services_by_entity()
    assert set(by_entity) == {"Invoice", "Customer"}
    for entity_name, service in by_entity.items():
        assert service.entity_name == entity_name


def test_custom_services_have_no_entity_and_are_skipped() -> None:
    """A non-CRUD service carries no `entity_name` — it must not pollute the view."""
    factory = ServiceFactory({"Invoice": _Invoice})
    factory.create_all_services(
        [
            _crud_spec("list_invoices", OperationKind.LIST, "Invoice"),
            ServiceSpec(
                name="recalculate_totals",
                domain_operation=DomainOperation(kind=OperationKind.CUSTOM, entity=None),
            ),
        ]
    )
    by_entity = factory.services_by_entity()
    assert set(by_entity) == {"Invoice"}
