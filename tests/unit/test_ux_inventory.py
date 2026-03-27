"""Tests for UX interaction inventory generation."""

from pathlib import Path

from dazzle.testing.ux.inventory import (
    Interaction,
    InteractionClass,
    generate_inventory,
)


class TestInteractionModel:
    def test_interaction_has_required_fields(self) -> None:
        i = Interaction(
            cls=InteractionClass.PAGE_LOAD,
            entity="Task",
            persona="admin",
            surface="task_list",
            description="Load task list as admin",
        )
        assert i.cls == InteractionClass.PAGE_LOAD
        assert i.entity == "Task"
        assert i.persona == "admin"

    def test_interaction_id_is_deterministic(self) -> None:
        a = Interaction(
            cls=InteractionClass.PAGE_LOAD,
            entity="Task",
            persona="admin",
            surface="task_list",
            description="Load task list",
        )
        b = Interaction(
            cls=InteractionClass.PAGE_LOAD,
            entity="Task",
            persona="admin",
            surface="task_list",
            description="Load task list",
        )
        assert a.interaction_id == b.interaction_id


class TestInventoryFromAppSpec:
    def test_simple_task_generates_interactions(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        inventory = generate_inventory(appspec)
        assert len(inventory) > 0

    def test_inventory_includes_page_loads(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        inventory = generate_inventory(appspec)
        page_loads = [i for i in inventory if i.cls == InteractionClass.PAGE_LOAD]
        assert len(page_loads) > 0

    def test_inventory_covers_all_entities(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        inventory = generate_inventory(appspec)
        entities_covered = {i.entity for i in inventory if i.entity}
        # Every entity with a surface should appear in the inventory
        surfaced_entities = {s.entity_ref for s in appspec.surfaces if s.entity_ref}
        assert surfaced_entities.issubset(entities_covered)

    def test_inventory_covers_all_personas(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        inventory = generate_inventory(appspec)
        personas_covered = {i.persona for i in inventory if i.persona}
        dsl_personas = {p.id for p in appspec.personas}
        # Every persona should appear at least once
        if dsl_personas:
            assert dsl_personas.issubset(personas_covered)

    def test_coverage_metric(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        inventory = generate_inventory(appspec)
        # All start untested
        assert all(i.status == "pending" for i in inventory)
        total = len(inventory)
        assert total > 0
