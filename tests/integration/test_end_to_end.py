"""Comprehensive end-to-end integration tests."""

from pathlib import Path

import pytest

from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.parser import parse_modules


def test_full_pipeline_dsl_to_appspec(tmp_path: Path):
    """Test complete pipeline: DSL → Parse → Link → Validate."""

    # Step 1: Create DSL file
    dsl_file = tmp_path / "app.dsl"
    dsl_file.write_text(
        """
module myapp.core

app myapp "My Application"

entity User "User":
  id: uuid pk
  email: email unique required
  name: str(200) required
  created_at: datetime auto_add

entity Post "Post":
  id: uuid pk
  title: str(300) required
  content: text
  author: ref User required
  published: bool=false
  created_at: datetime auto_add

  index author
  unique title,author

surface user_list "Users":
  uses entity User
  mode: list

  section main "Users":
    field email "Email"
    field name "Name"
    field created_at "Joined"

surface post_create "Create Post":
  uses entity Post
  mode: create

  section main "New Post":
    field title "Title"
    field content "Content"
    field author "Author"
"""
    )

    # Step 2: Parse DSL
    modules = parse_modules([dsl_file])
    assert len(modules) == 1
    module = modules[0]
    assert module.name == "myapp.core"

    # Step 3: Link modules
    appspec = build_appspec(modules, "myapp.core")
    assert appspec.name == "myapp"
    assert appspec.title == "My Application"

    # Step 4: Validate
    errors, warnings = lint_appspec(appspec, extended=True)
    assert len(errors) == 0, f"Unexpected errors: {errors}"
    # May have warnings (unused entities, etc.) but no errors

    # Step 5: Check IR structure
    assert len(appspec.domain.entities) == 2
    entity_names = {e.name for e in appspec.domain.entities}
    assert entity_names == {"User", "Post"}

    # Check Post entity has author reference
    post = appspec.get_entity("Post")
    assert post is not None
    author_field = post.get_field("author")
    assert author_field is not None
    assert author_field.type.kind.value == "ref"
    assert author_field.type.ref_entity == "User"

    # Check surfaces
    assert len(appspec.surfaces) == 2
    surface_names = {s.name for s in appspec.surfaces}
    assert surface_names == {"user_list", "post_create"}


def test_multi_module_project(tmp_path: Path):
    """Test multi-module project with cross-module references."""

    # Create module 1: auth
    auth_dsl = tmp_path / "auth.dsl"
    auth_dsl.write_text(
        """
module myapp.auth

entity AuthToken "Auth Token":
  id: uuid pk
  token: str(500) required unique
  expires_at: datetime required
"""
    )

    # Create module 2: core (uses auth)
    core_dsl = tmp_path / "core.dsl"
    core_dsl.write_text(
        """
module myapp.core

use myapp.auth

app myapp "My App"

entity User "User":
  id: uuid pk
  email: email required
  current_token: ref AuthToken optional

surface user_list "Users":
  uses entity User
  mode: list

  section main:
    field email
"""
    )

    # Parse both modules
    modules = parse_modules([auth_dsl, core_dsl])
    assert len(modules) == 2

    # Link with dependency resolution
    appspec = build_appspec(modules, "myapp.core")

    # Should have both entities
    assert len(appspec.domain.entities) == 2
    entity_names = {e.name for e in appspec.domain.entities}
    assert entity_names == {"AuthToken", "User"}

    # Check cross-module reference
    user = appspec.get_entity("User")
    token_field = user.get_field("current_token")
    assert token_field.type.kind.value == "ref"
    assert token_field.type.ref_entity == "AuthToken"

    # Validate
    errors, warnings = lint_appspec(appspec)
    assert len(errors) == 0


def test_error_handling_invalid_reference(tmp_path: Path):
    """Test that invalid references are caught during linking."""

    dsl_file = tmp_path / "app.dsl"
    dsl_file.write_text(
        """
module test.app

app test "Test"

entity Post:
  id: uuid pk
  author: ref NonExistentUser required
"""
    )

    modules = parse_modules([dsl_file])

    # Should raise LinkError for invalid reference
    from dazzle.core.errors import LinkError

    with pytest.raises(LinkError) as exc_info:
        build_appspec(modules, "test.app")

    assert "NonExistentUser" in str(exc_info.value)


def test_validation_catches_semantic_errors(tmp_path: Path):
    """Test that validator catches semantic errors."""

    dsl_file = tmp_path / "app.dsl"
    dsl_file.write_text(
        """
module test.app

app test "Test"

entity Task:
  id: uuid pk
  title: str(200) required

surface task_detail:
  uses entity Task
  mode: view

  section main:
    field nonexistent_field
"""
    )

    modules = parse_modules([dsl_file])
    appspec = build_appspec(modules, "test.app")

    # Should have validation error
    errors, warnings = lint_appspec(appspec)
    assert len(errors) > 0
    assert any("nonexistent_field" in err for err in errors)
