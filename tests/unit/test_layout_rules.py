"""Tests for layout relevance rules.

Covers the four layout rules:
1. Kanban: entity with state machine, no kanban workspace region
2. Timeline: entity with date/datetime fields, no timeline workspace region
3. Related groups: view surface with 3+ referencing entities, no related_groups
4. Multi-section: create/edit surface with single section and 5+ elements
"""

from dazzle.core.discovery.layout_rules import check_layout_relevance
from dazzle.core.ir.domain import EntitySpec
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.state_machine import StateMachineSpec, StateTransition
from dazzle.core.ir.surfaces import (
    RelatedDisplayMode,
    RelatedGroup,
    SurfaceElement,
    SurfaceMode,
    SurfaceSection,
    SurfaceSpec,
)
from dazzle.core.ir.workspaces import DisplayMode, WorkspaceRegion, WorkspaceSpec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _field(name: str, kind: FieldTypeKind, **kwargs) -> FieldSpec:
    """Create a minimal FieldSpec."""
    return FieldSpec(name=name, type=FieldType(kind=kind, **kwargs))


def _entity(
    name: str,
    fields: list[FieldSpec] | None = None,
    state_machine: StateMachineSpec | None = None,
) -> EntitySpec:
    """Create a minimal EntitySpec."""
    return EntitySpec(name=name, fields=fields or [], state_machine=state_machine)


def _state_machine() -> StateMachineSpec:
    """Return a minimal StateMachineSpec with at least one transition."""
    return StateMachineSpec(
        status_field="status",
        states=["draft", "active", "done"],
        transitions=[
            StateTransition(from_state="draft", to_state="active"),
            StateTransition(from_state="active", to_state="done"),
        ],
    )


def _workspace_with_region(
    name: str,
    source: str,
    display: DisplayMode,
) -> WorkspaceSpec:
    """Create a WorkspaceSpec with a single region."""
    region = WorkspaceRegion(name="main", source=source, display=display)
    return WorkspaceSpec(name=name, regions=[region])


def _view_surface(
    name: str,
    entity_ref: str,
    related_groups: list[RelatedGroup] | None = None,
) -> SurfaceSpec:
    """Create a minimal VIEW surface."""
    return SurfaceSpec(
        name=name,
        entity_ref=entity_ref,
        mode=SurfaceMode.VIEW,
        sections=[],
        related_groups=related_groups or [],
    )


def _form_surface(
    name: str,
    entity_ref: str,
    mode: SurfaceMode,
    num_fields: int,
    num_sections: int = 1,
) -> SurfaceSpec:
    """Create a CREATE/EDIT surface with the given field count spread across sections."""
    fields_per_section = num_fields // num_sections
    sections = []
    for s_idx in range(num_sections):
        count = (
            fields_per_section
            if s_idx < num_sections - 1
            else num_fields - fields_per_section * s_idx
        )
        elements = [SurfaceElement(field_name=f"field_{s_idx}_{i}") for i in range(count)]
        sections.append(SurfaceSection(name=f"section_{s_idx}", elements=elements))
    return SurfaceSpec(name=name, entity_ref=entity_ref, mode=mode, sections=sections)


# ---------------------------------------------------------------------------
# Rule 1: Kanban
# ---------------------------------------------------------------------------


class TestKanbanRule:
    def test_entity_with_transitions_no_kanban_returns_relevance(self):
        """Entity with state machine and no kanban region → kanban relevance."""
        entity = _entity("Task", state_machine=_state_machine())
        results = check_layout_relevance([entity], [], [])
        assert len(results) == 1
        r = results[0]
        assert r.capability == "kanban display mode"
        assert r.category == "layout"
        assert r.kg_entity == "capability:layout_kanban"
        assert "Task" in r.context
        assert r.examples == []

    def test_entity_with_transitions_and_kanban_region_no_relevance(self):
        """Entity with state machine AND a kanban workspace region → no kanban relevance."""
        entity = _entity("Task", state_machine=_state_machine())
        workspace = _workspace_with_region("board", "Task", DisplayMode.KANBAN)
        results = check_layout_relevance([entity], [], [workspace])
        kanban_results = [r for r in results if r.kg_entity == "capability:layout_kanban"]
        assert kanban_results == []

    def test_entity_without_transitions_no_kanban_relevance(self):
        """Entity without state machine → no kanban relevance."""
        entity = _entity("Product", fields=[_field("name", FieldTypeKind.STR)])
        results = check_layout_relevance([entity], [], [])
        kanban_results = [r for r in results if r.kg_entity == "capability:layout_kanban"]
        assert kanban_results == []

    def test_context_mentions_entity_and_state_machine(self):
        entity = _entity("Order", state_machine=_state_machine())
        results = check_layout_relevance([entity], [], [])
        r = next(r for r in results if r.kg_entity == "capability:layout_kanban")
        assert "Order" in r.context
        assert "state machine" in r.context


# ---------------------------------------------------------------------------
# Rule 2: Timeline
# ---------------------------------------------------------------------------


class TestTimelineRule:
    def test_entity_with_date_field_no_timeline_returns_relevance(self):
        """Entity with DATE field and no timeline workspace region → timeline relevance."""
        entity = _entity("Event", fields=[_field("starts_on", FieldTypeKind.DATE)])
        results = check_layout_relevance([entity], [], [])
        timeline_results = [r for r in results if r.kg_entity == "capability:layout_timeline"]
        assert len(timeline_results) == 1
        r = timeline_results[0]
        assert r.capability == "timeline display mode"
        assert r.category == "layout"
        assert "Event" in r.context

    def test_entity_with_datetime_field_no_timeline_returns_relevance(self):
        """Entity with DATETIME field and no timeline workspace region → timeline relevance."""
        entity = _entity("Meeting", fields=[_field("scheduled_at", FieldTypeKind.DATETIME)])
        results = check_layout_relevance([entity], [], [])
        timeline_results = [r for r in results if r.kg_entity == "capability:layout_timeline"]
        assert len(timeline_results) == 1

    def test_entity_with_date_field_and_timeline_region_no_relevance(self):
        """Entity with date field AND a timeline workspace region → no timeline relevance."""
        entity = _entity("Event", fields=[_field("starts_on", FieldTypeKind.DATE)])
        workspace = _workspace_with_region("schedule_view", "Event", DisplayMode.TIMELINE)
        results = check_layout_relevance([entity], [], [workspace])
        timeline_results = [r for r in results if r.kg_entity == "capability:layout_timeline"]
        assert timeline_results == []

    def test_entity_without_date_fields_no_timeline_relevance(self):
        """Entity with only string/int fields → no timeline relevance."""
        entity = _entity(
            "Product",
            fields=[
                _field("name", FieldTypeKind.STR),
                _field("quantity", FieldTypeKind.INT),
            ],
        )
        results = check_layout_relevance([entity], [], [])
        timeline_results = [r for r in results if r.kg_entity == "capability:layout_timeline"]
        assert timeline_results == []

    def test_context_mentions_entity_and_date(self):
        entity = _entity("Deadline", fields=[_field("due_date", FieldTypeKind.DATE)])
        results = check_layout_relevance([entity], [], [])
        r = next(r for r in results if r.kg_entity == "capability:layout_timeline")
        assert "Deadline" in r.context
        assert "date" in r.context.lower()


# ---------------------------------------------------------------------------
# Rule 3: Related groups
# ---------------------------------------------------------------------------


class TestRelatedGroupsRule:
    def test_view_surface_with_3plus_referencing_entities_no_related_groups(self):
        """VIEW surface with 3+ REF-ing entities and no related_groups → related groups relevance."""
        # Three entities all have REF fields pointing to Client
        client = _entity("Client", fields=[_field("name", FieldTypeKind.STR)])
        order = _entity("Order", fields=[_field("client", FieldTypeKind.REF, ref_entity="Client")])
        invoice = _entity(
            "Invoice", fields=[_field("client", FieldTypeKind.REF, ref_entity="Client")]
        )
        contact = _entity(
            "Contact", fields=[_field("client", FieldTypeKind.REF, ref_entity="Client")]
        )
        view = _view_surface("client_view", "Client")
        results = check_layout_relevance([client, order, invoice, contact], [view], [])
        related_results = [r for r in results if r.kg_entity == "capability:layout_related_groups"]
        assert len(related_results) == 1
        r = related_results[0]
        assert r.capability == "related group display modes"
        assert r.category == "layout"
        assert "client_view" in r.context or "Client" in r.context

    def test_view_surface_with_existing_related_groups_no_relevance(self):
        """VIEW surface with 3+ REF-ing entities but related_groups present → no relevance."""
        client = _entity("Client", fields=[_field("name", FieldTypeKind.STR)])
        order = _entity("Order", fields=[_field("client", FieldTypeKind.REF, ref_entity="Client")])
        invoice = _entity(
            "Invoice", fields=[_field("client", FieldTypeKind.REF, ref_entity="Client")]
        )
        contact = _entity(
            "Contact", fields=[_field("client", FieldTypeKind.REF, ref_entity="Client")]
        )
        existing_group = RelatedGroup(
            name="related", display=RelatedDisplayMode.TABLE, show=["Order"]
        )
        view = _view_surface("client_view", "Client", related_groups=[existing_group])
        results = check_layout_relevance([client, order, invoice, contact], [view], [])
        related_results = [r for r in results if r.kg_entity == "capability:layout_related_groups"]
        assert related_results == []

    def test_view_surface_with_only_2_referencing_entities_no_relevance(self):
        """VIEW surface with only 2 REF-ing entities (below threshold) → no relevance."""
        project = _entity("Project", fields=[_field("name", FieldTypeKind.STR)])
        task = _entity("Task", fields=[_field("project", FieldTypeKind.REF, ref_entity="Project")])
        note = _entity("Note", fields=[_field("project", FieldTypeKind.REF, ref_entity="Project")])
        view = _view_surface("project_view", "Project")
        results = check_layout_relevance([project, task, note], [view], [])
        related_results = [r for r in results if r.kg_entity == "capability:layout_related_groups"]
        assert related_results == []

    def test_non_view_surface_not_checked(self):
        """Related groups rule only fires for VIEW surfaces."""
        client = _entity("Client", fields=[_field("name", FieldTypeKind.STR)])
        order = _entity("Order", fields=[_field("client", FieldTypeKind.REF, ref_entity="Client")])
        invoice = _entity(
            "Invoice", fields=[_field("client", FieldTypeKind.REF, ref_entity="Client")]
        )
        contact = _entity(
            "Contact", fields=[_field("client", FieldTypeKind.REF, ref_entity="Client")]
        )
        # LIST surface, not VIEW
        list_surface = SurfaceSpec(
            name="client_list",
            entity_ref="Client",
            mode=SurfaceMode.LIST,
            sections=[],
        )
        results = check_layout_relevance([client, order, invoice, contact], [list_surface], [])
        related_results = [r for r in results if r.kg_entity == "capability:layout_related_groups"]
        assert related_results == []

    def test_exactly_3_referencing_entities_triggers_rule(self):
        """Exactly 3 referencing entities (at threshold) → fires."""
        hub = _entity("Hub", fields=[_field("name", FieldTypeKind.STR)])
        e1 = _entity("E1", fields=[_field("hub", FieldTypeKind.REF, ref_entity="Hub")])
        e2 = _entity("E2", fields=[_field("hub", FieldTypeKind.REF, ref_entity="Hub")])
        e3 = _entity("E3", fields=[_field("hub", FieldTypeKind.REF, ref_entity="Hub")])
        view = _view_surface("hub_view", "Hub")
        results = check_layout_relevance([hub, e1, e2, e3], [view], [])
        related_results = [r for r in results if r.kg_entity == "capability:layout_related_groups"]
        assert len(related_results) == 1


# ---------------------------------------------------------------------------
# Rule 4: Multi-section form
# ---------------------------------------------------------------------------


class TestMultiSectionRule:
    def test_create_surface_with_6_fields_single_section_returns_relevance(self):
        """CREATE surface with 6 fields in a single section → multi-section relevance."""
        entity = _entity("Registration")
        surface = _form_surface("reg_create", "Registration", SurfaceMode.CREATE, num_fields=6)
        results = check_layout_relevance([entity], [surface], [])
        ms_results = [r for r in results if r.kg_entity == "capability:layout_multi_section"]
        assert len(ms_results) == 1
        r = ms_results[0]
        assert r.capability == "multi-section form"
        assert r.category == "layout"
        assert "reg_create" in r.context
        assert r.examples == []

    def test_edit_surface_with_5_fields_single_section_returns_relevance(self):
        """EDIT surface with exactly 5 fields in a single section → fires (≥5 threshold)."""
        entity = _entity("Profile")
        surface = _form_surface("profile_edit", "Profile", SurfaceMode.EDIT, num_fields=5)
        results = check_layout_relevance([entity], [surface], [])
        ms_results = [r for r in results if r.kg_entity == "capability:layout_multi_section"]
        assert len(ms_results) == 1

    def test_create_surface_with_multiple_sections_no_relevance(self):
        """CREATE surface already split into 2+ sections → no multi-section relevance."""
        entity = _entity("BigForm")
        surface = _form_surface(
            "bigform_create", "BigForm", SurfaceMode.CREATE, num_fields=6, num_sections=2
        )
        results = check_layout_relevance([entity], [surface], [])
        ms_results = [r for r in results if r.kg_entity == "capability:layout_multi_section"]
        assert ms_results == []

    def test_create_surface_with_4_fields_single_section_no_relevance(self):
        """CREATE surface with only 4 fields → below threshold, no relevance."""
        entity = _entity("Simple")
        surface = _form_surface("simple_create", "Simple", SurfaceMode.CREATE, num_fields=4)
        results = check_layout_relevance([entity], [surface], [])
        ms_results = [r for r in results if r.kg_entity == "capability:layout_multi_section"]
        assert ms_results == []

    def test_view_surface_not_checked_for_multi_section(self):
        """VIEW surface with many sections/elements is not checked for multi-section rule."""
        entity = _entity("Report")
        # A VIEW surface with many elements in a single section
        elements = [SurfaceElement(field_name=f"field_{i}") for i in range(10)]
        section = SurfaceSection(name="main", elements=elements)
        surface = SurfaceSpec(
            name="report_view", entity_ref="Report", mode=SurfaceMode.VIEW, sections=[section]
        )
        results = check_layout_relevance([entity], [surface], [])
        ms_results = [r for r in results if r.kg_entity == "capability:layout_multi_section"]
        assert ms_results == []

    def test_context_mentions_field_count_and_surface_name(self):
        entity = _entity("App")
        surface = _form_surface("app_create", "App", SurfaceMode.CREATE, num_fields=7)
        results = check_layout_relevance([entity], [surface], [])
        r = next(r for r in results if r.kg_entity == "capability:layout_multi_section")
        assert "app_create" in r.context
        assert "7" in r.context


# ---------------------------------------------------------------------------
# Integration / combined scenarios
# ---------------------------------------------------------------------------


class TestLayoutRulesCombined:
    def test_empty_inputs_return_empty_list(self):
        results = check_layout_relevance([], [], [])
        assert results == []

    def test_all_rules_can_fire_simultaneously(self):
        """All four rules fire in a single call."""
        # Kanban entity
        kanban_entity = _entity("Ticket", state_machine=_state_machine())

        # Timeline entity
        timeline_entity = _entity("Appointment", fields=[_field("date", FieldTypeKind.DATE)])

        # Related groups setup
        project = _entity("Project", fields=[_field("name", FieldTypeKind.STR)])
        e1 = _entity("Task", fields=[_field("project", FieldTypeKind.REF, ref_entity="Project")])
        e2 = _entity("Bug", fields=[_field("project", FieldTypeKind.REF, ref_entity="Project")])
        e3 = _entity("Note", fields=[_field("project", FieldTypeKind.REF, ref_entity="Project")])
        view = _view_surface("project_view", "Project")

        # Multi-section form
        form_surface = _form_surface("reg_create", "Registration", SurfaceMode.CREATE, num_fields=8)

        all_entities = [kanban_entity, timeline_entity, project, e1, e2, e3]
        all_surfaces = [view, form_surface]
        results = check_layout_relevance(all_entities, all_surfaces, [])

        kg_entities = {r.kg_entity for r in results}
        assert "capability:layout_kanban" in kg_entities
        assert "capability:layout_timeline" in kg_entities
        assert "capability:layout_related_groups" in kg_entities
        assert "capability:layout_multi_section" in kg_entities
