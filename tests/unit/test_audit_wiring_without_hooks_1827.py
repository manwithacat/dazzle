"""#1827 — `audit on X:` callbacks are wired whether or not the app has
project hooks. They used to be registered inside ``_wire_service_hooks``
below its no-``hooks/`` early return, so hook-less apps audited nothing."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.http.runtime.server import DazzleBackendApp, ServerConfig

SUPPORT_TICKETS = Path(__file__).resolve().parents[2] / "examples" / "support_tickets"


def test_hookless_app_wires_audit_callbacks() -> None:
    assert not (SUPPORT_TICKETS / "hooks").exists()
    spec = load_project_appspec(SUPPORT_TICKETS)
    audited = {a.entity for a in spec.audits}
    assert audited, "support_tickets is the audit probe"

    builder = DazzleBackendApp(
        spec,
        config=ServerConfig(database_url="postgresql://example/test", project_root=SUPPORT_TICKETS),
    )
    builder._create_app()
    builder._setup_models()
    builder._setup_services()

    services = builder.services_by_entity()
    for entity in audited:
        service = services[entity]
        assert service._on_created_callbacks, entity
        assert service._on_updated_callbacks, entity
        assert service._on_deleted_callbacks, entity
