"""Tests for the SPEC.md + docs/specs/ scaffold (#1106 Proposal 2).

`dazzle init` lays down the spec drift-detection convention from day one:

- `SPEC.md` carries a ``Domain map`` placeholder + a "Keeping spec and DSL
  in sync" section that points to ``dazzle spec status``.
- ``docs/specs/`` exists with a README describing the per-feature
  design-doc convention.

This pins both pieces so a future template edit can't silently delete them.
"""

from pathlib import Path

from dazzle.core.init_impl.spec import create_spec_template, create_specs_scaffold


def test_spec_template_includes_domain_map_section(tmp_path: Path) -> None:
    """SPEC.md must scaffold a Domain map table for drift tracking."""
    create_spec_template(tmp_path, "my_app", "My App")
    spec = (tmp_path / "SPEC.md").read_text()
    assert "## Domain map" in spec
    assert "| Domain | Entities | Design doc |" in spec
    # The placeholder explains how the table gets populated.
    assert "(populated as you add entities" in spec


def test_spec_template_documents_dazzle_spec_status(tmp_path: Path) -> None:
    """The 'Keeping spec and DSL in sync' section points at the drift CLI."""
    create_spec_template(tmp_path, "my_app", "My App")
    spec = (tmp_path / "SPEC.md").read_text()
    assert "Keeping spec and DSL in sync" in spec
    assert "dazzle spec status" in spec


def test_specs_scaffold_creates_directory_and_readme(tmp_path: Path) -> None:
    """`dazzle init` creates docs/specs/ with a README describing the convention."""
    create_specs_scaffold(tmp_path)
    assert (tmp_path / "docs" / "specs").is_dir()
    readme = (tmp_path / "docs" / "specs" / "README.md").read_text()
    assert "Per-feature design docs" in readme
    assert "YYYY-MM-DD-<slug>.md" in readme
    assert "dazzle spec status" in readme


def test_specs_scaffold_is_idempotent(tmp_path: Path) -> None:
    """Re-running create_specs_scaffold must not clobber an existing README."""
    create_specs_scaffold(tmp_path)
    readme = tmp_path / "docs" / "specs" / "README.md"
    readme.write_text("CUSTOM CONTENT")

    create_specs_scaffold(tmp_path)
    assert readme.read_text() == "CUSTOM CONTENT"


def test_init_project_wires_specs_scaffold(tmp_path: Path) -> None:
    """End-to-end: init_project lays down docs/specs/README.md alongside SPEC.md."""
    from dazzle.core.init_impl import init_project

    target = tmp_path / "myproj"
    init_project(
        project_name="myproj",
        target_dir=target,
        title="My Project",
        from_example=None,
        no_llm=True,
    )
    assert (target / "SPEC.md").is_file()
    assert (target / "docs" / "specs").is_dir()
    assert (target / "docs" / "specs" / "README.md").is_file()
