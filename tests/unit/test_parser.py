#!/usr/bin/env python3
"""Test parser implementation."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl

# Test entity parsing
test_dsl = """
module test.core

app test_app "Test Application"

entity User "User":
  id: uuid pk
  email: email unique required
  name: str(120) required
  age: int optional
  created_at: datetime auto_add

  index email
  unique email

entity Post "Post":
  id: uuid pk
  author: ref User required
  title: str(200) required
  content: text
  status: enum[draft,published,archived]=draft
  views: int=0
  metadata: json

  index author
"""


def main():
    print("Testing lexer and parser...")
    print("=" * 60)

    module_name, app_name, app_title, _, uses, fragment = parse_dsl(test_dsl, Path("test.dsl"))

    print(f"Module: {module_name}")
    print(f"App: {app_name} - {app_title}")
    print(f"Uses: {uses}")
    print()

    print(f"Entities parsed: {len(fragment.entities)}")
    for entity in fragment.entities:
        print(f"\n  Entity: {entity.name} ({entity.title})")
        print(f"    Fields: {len(entity.fields)}")
        for field in entity.fields:
            print(
                f"      - {field.name}: {field.type.kind.value} "
                + f"(modifiers: {[m.value for m in field.modifiers]}, "
                + f"default: {field.default})"
            )
        print(f"    Constraints: {len(entity.constraints)}")
        for constraint in entity.constraints:
            print(f"      - {constraint.kind.value}: {constraint.fields}")

    print("\n" + "=" * 60)
    print("✅ Parser test passed!")


class TestFieldTypes:
    """Tests for field type parsing (v0.9.5)."""

    def test_money_field_default_currency(self):
        """Test money field with default GBP currency."""
        dsl = """
module test.core
app MyApp "My App"

entity Invoice "Invoice":
  id: uuid pk
  total: money required
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        invoice = fragment.entities[0]
        total_field = next(f for f in invoice.fields if f.name == "total")

        assert total_field.type.kind.value == "money"
        assert total_field.type.currency_code == "GBP"

    def test_money_field_custom_currency(self):
        """Test money field with custom currency."""
        dsl = """
module test.core
app MyApp "My App"

entity Invoice "Invoice":
  id: uuid pk
  total: money(USD) required
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        invoice = fragment.entities[0]
        total_field = next(f for f in invoice.fields if f.name == "total")

        assert total_field.type.kind.value == "money"
        assert total_field.type.currency_code == "USD"

    def test_file_field(self):
        """Test file field type."""
        dsl = """
module test.core
app MyApp "My App"

entity Document "Document":
  id: uuid pk
  attachment: file
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        doc = fragment.entities[0]
        attachment_field = next(f for f in doc.fields if f.name == "attachment")

        assert attachment_field.type.kind.value == "file"

    def test_url_field(self):
        """Test url field type."""
        dsl = """
module test.core
app MyApp "My App"

entity Link "Link":
  id: uuid pk
  target: url required
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        link = fragment.entities[0]
        target_field = next(f for f in link.fields if f.name == "target")

        assert target_field.type.kind.value == "url"

    def test_has_many_via_junction(self):
        """Test many-to-many relationship via junction table."""
        dsl = """
module test.core
app MyApp "My App"

entity Client "Client":
  id: uuid pk
  name: str(200) required
  contacts: has_many Contact via ClientContact

entity Contact "Contact":
  id: uuid pk
  email: email required

entity ClientContact "Client Contact":
  id: uuid pk
  client: ref Client
  contact: ref Contact
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        client = fragment.entities[0]
        contacts_field = next(f for f in client.fields if f.name == "contacts")

        assert contacts_field.type.kind.value == "has_many"
        assert contacts_field.type.ref_entity == "Contact"
        assert contacts_field.type.via_entity == "ClientContact"


class TestWorkspaceDisplayModes:
    """Tests for workspace display mode parsing (v0.9.5)."""

    def test_kanban_display_mode(self):
        """Test kanban display mode."""
        dsl = """
module test.core
app MyApp "My App"

entity Task "Task":
  id: uuid pk
  status: enum[todo, in_progress, done]

workspace task_board "Task Board":
  tasks:
    source: Task
    display: kanban
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        workspace = fragment.workspaces[0]
        region = workspace.regions[0]

        assert region.display.value == "kanban"

    def test_bar_chart_display_mode(self):
        """Test bar_chart display mode."""
        dsl = """
module test.core
app MyApp "My App"

entity Sale "Sale":
  id: uuid pk
  amount: decimal(10,2)

workspace sales_dashboard "Sales Dashboard":
  chart:
    source: Sale
    display: bar_chart
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        workspace = fragment.workspaces[0]
        region = workspace.regions[0]

        assert region.display.value == "bar_chart"

    def test_funnel_chart_display_mode(self):
        """Test funnel_chart display mode."""
        dsl = """
module test.core
app MyApp "My App"

entity Lead "Lead":
  id: uuid pk
  stage: enum[awareness, interest, decision, action]

workspace pipeline "Pipeline":
  funnel:
    source: Lead
    display: funnel_chart
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        workspace = fragment.workspaces[0]
        region = workspace.regions[0]

        assert region.display.value == "funnel_chart"


class TestAppConfig:
    """Tests for app config block parsing (v0.9.5)."""

    def test_app_config_basic(self):
        """Test basic app config with all options."""
        dsl = """
module test.core

app MyApp "My Application":
  description: "A test application"
  multi_tenant: true
  audit_trail: true

entity User "User":
  id: uuid pk
  name: str(100) required
"""
        module_name, app_name, app_title, app_config, uses, fragment = parse_dsl(
            dsl, Path("test.dsl")
        )

        assert app_name == "MyApp"
        assert app_title == "My Application"
        assert app_config is not None
        assert app_config.description == "A test application"
        assert app_config.multi_tenant is True
        assert app_config.audit_trail is True
        assert len(fragment.entities) == 1

    def test_app_config_partial(self):
        """Test app config with only some options."""
        dsl = """
module test.core

app MyApp "My Application":
  description: "Just a description"

entity User "User":
  id: uuid pk
"""
        _, _, _, app_config, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert app_config is not None
        assert app_config.description == "Just a description"
        assert app_config.multi_tenant is False  # Default
        assert app_config.audit_trail is False  # Default
        assert len(fragment.entities) == 1

    def test_app_config_features(self):
        """Test app config with custom features."""
        dsl = """
module test.core

app MyApp "My Application":
  multi_tenant: true
  custom_feature: "enabled"
  another_flag: true

entity User "User":
  id: uuid pk
"""
        _, _, _, app_config, _, _ = parse_dsl(dsl, Path("test.dsl"))

        assert app_config is not None
        assert app_config.multi_tenant is True
        assert app_config.features.get("custom_feature") == "enabled"
        assert app_config.features.get("another_flag") is True

    def test_app_without_config(self):
        """Test app declaration without config body."""
        dsl = """
module test.core

app MyApp "My Application"

entity User "User":
  id: uuid pk
"""
        _, app_name, app_title, app_config, _, _ = parse_dsl(dsl, Path("test.dsl"))

        assert app_name == "MyApp"
        assert app_title == "My Application"
        assert app_config is None


if __name__ == "__main__":
    main()
