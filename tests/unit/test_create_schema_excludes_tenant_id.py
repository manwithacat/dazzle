"""Create/update input schemas omit the framework-managed partition key (Plan 1d)."""

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.http.converters.entity_converter import convert_entities
from dazzle.http.runtime.model_generator import generate_create_schema, generate_update_schema


def _project_entity():
    """The back-EntitySpec Project (what the runtime feeds the schema builders)."""
    appspec = load_project_appspec(Path("fixtures/tenant_rls"))
    pk = appspec.tenancy.isolation.partition_key
    entity = next(e for e in convert_entities(appspec.domain.entities) if e.name == "Project")
    return entity, pk


def test_create_schema_omits_partition_key_when_scoped() -> None:
    entity, pk = _project_entity()
    model = generate_create_schema(entity, partition_key=pk, tenant_scoped=True)
    assert pk not in model.model_fields  # server-supplied, not client input


def test_update_schema_omits_partition_key_when_scoped() -> None:
    entity, pk = _project_entity()
    model = generate_update_schema(entity, partition_key=pk, tenant_scoped=True)
    assert pk not in model.model_fields


def test_non_scoped_call_keeps_partition_key_field() -> None:
    # Back-compat: without tenant_scoped, the field is NOT excluded.
    entity, pk = _project_entity()
    model = generate_create_schema(entity, partition_key=pk, tenant_scoped=False)
    assert pk in model.model_fields
