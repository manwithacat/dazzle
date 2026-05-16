"""Tests for the spec-drift strict guard (#1106 Proposal 3).

Two layers:

- ``_extract_domain_map_entities`` parses the ``## Domain map`` markdown
  table in SPEC.md. The table is the only place that satisfies the
  strict check — prose mentions elsewhere don't count.
- ``_compute_drift`` populates ``missing_from_domain_map`` with DSL
  entities that aren't in any table row. The ``--fail-on-strict`` CLI
  flag (and the ``[spec] strict = true`` manifest flag) exit non-zero
  when this list is non-empty.
"""

from types import SimpleNamespace

from dazzle.cli.spec import (
    _compute_drift,
    _extract_domain_map_entities,
    _manifest_strict_enabled,
)


def _fake_appspec(*entity_names: str) -> object:
    entities = [SimpleNamespace(name=n) for n in entity_names]
    return SimpleNamespace(domain=SimpleNamespace(entities=entities))


# ---------------------------------------------------------------------------
# Domain-map table parser
# ---------------------------------------------------------------------------


def test_extract_domain_map_finds_entities_in_rows() -> None:
    spec = """\
# My Project

## Domain map

| Domain | Entities | Design doc |
|---|---|---|
| Orders | Order, OrderItem | [orders.md](docs/specs/orders.md) |
| Users | User | [users.md](docs/specs/users.md) |
"""
    entities = _extract_domain_map_entities(spec)
    assert entities == {"Order", "OrderItem", "User"}


def test_extract_domain_map_ignores_placeholder_row() -> None:
    """The `(populated as you add entities)` placeholder row from
    `dazzle init` must not yield phantom entities."""
    spec = """\
## Domain map

| Domain | Entities | Design doc |
|---|---|---|
| _(populated as you add entities — start in `docs/specs/`)_ | | |
"""
    assert _extract_domain_map_entities(spec) == set()


def test_extract_domain_map_returns_empty_when_no_heading() -> None:
    spec = "# Some unrelated content\n\nNo domain map here."
    assert _extract_domain_map_entities(spec) == set()


def test_extract_domain_map_stops_at_next_heading() -> None:
    """The table parse must stop before the next section heading so a
    later table doesn't get conflated with the Domain map."""
    spec = """\
## Domain map

| Domain | Entities | Design doc |
|---|---|---|
| Orders | Order | [o.md](docs/specs/o.md) |

## Some other section

| key | val |
|---|---|
| Forbidden | NotAnEntity |
"""
    assert _extract_domain_map_entities(spec) == {"Order"}


def test_extract_domain_map_strips_backticks_and_asterisks() -> None:
    spec = """\
## Domain map

| Domain | Entities | Design doc |
|---|---|---|
| Auth | `User`, **Session** | x |
"""
    assert _extract_domain_map_entities(spec) == {"User", "Session"}


def test_extract_domain_map_skips_non_identifier_tokens() -> None:
    """Parenthesised placeholders, lowercase tokens, and slash/space-
    separated text don't survive the `^[A-Z][A-Za-z0-9_]*$` filter."""
    spec = """\
## Domain map

| Domain | Entities | Design doc |
|---|---|---|
| Future | (planned), some lowercase, Real |  x |
"""
    # `(planned)` (parenthesised) and `some lowercase` (lowercase
    # start) both fail the filter; only `Real` survives. ALL-CAPS
    # acronyms like `TBD` or `URL` do match — they're real Python
    # identifiers and could be legitimate entity names.
    assert _extract_domain_map_entities(spec) == {"Real"}


# ---------------------------------------------------------------------------
# _compute_drift — strict-mode field
# ---------------------------------------------------------------------------


def test_compute_drift_populates_missing_from_domain_map() -> None:
    """DSL entities that don't appear in any row of the Domain map
    table land in `missing_from_domain_map`, even when they're
    mentioned in prose."""
    appspec = _fake_appspec("Order", "User", "Invoice")
    spec = """\
Users place Orders. Invoices are computed nightly.

## Domain map

| Domain | Entities | Design doc |
|---|---|---|
| Orders | Order | docs/specs/orders.md |
"""
    report = _compute_drift(appspec, spec, spec_present=True)  # type: ignore[arg-type]
    # Prose mentions User and Invoice but the table only has Order →
    # strict mode flags User + Invoice as missing.
    assert sorted(report.missing_from_domain_map) == ["Invoice", "User"]
    assert "Order" in report.domain_map_entities
    # Loose `missing_from_spec` still passes (prose mentions are fine):
    assert report.missing_from_spec == []


def test_compute_drift_clean_when_every_entity_is_in_map() -> None:
    appspec = _fake_appspec("Order", "User")
    spec = """\
## Domain map

| Domain | Entities | Design doc |
|---|---|---|
| Orders | Order | docs/specs/orders.md |
| Auth | User | docs/specs/auth.md |
"""
    report = _compute_drift(appspec, spec, spec_present=True)  # type: ignore[arg-type]
    assert report.missing_from_domain_map == []


def test_compute_drift_strict_filters_framework_entities() -> None:
    """Framework-injected entities are excluded from the strict check
    just as they are from the loose check — projects shouldn't have
    to document AIJob/SystemHealth/etc. in their Domain map."""
    appspec = _fake_appspec("AIJob", "DeployHistory", "Order")
    spec = """\
## Domain map

| Domain | Entities | Design doc |
|---|---|---|
| Orders | Order | docs/specs/orders.md |
"""
    report = _compute_drift(appspec, spec, spec_present=True)  # type: ignore[arg-type]
    assert "AIJob" not in report.missing_from_domain_map
    assert "DeployHistory" not in report.missing_from_domain_map
    assert report.missing_from_domain_map == []


def test_compute_drift_strict_opt_in_includes_framework_entities() -> None:
    appspec = _fake_appspec("AIJob")
    spec = """\
## Domain map

| Domain | Entities | Design doc |
|---|---|---|
| Orders | Order | docs/specs/orders.md |
"""
    report = _compute_drift(appspec, spec, spec_present=True, include_framework_entities=True)  # type: ignore[arg-type]
    assert "AIJob" in report.missing_from_domain_map


# ---------------------------------------------------------------------------
# Manifest [spec] strict flag
# ---------------------------------------------------------------------------


def test_manifest_strict_returns_false_when_no_dazzle_toml(tmp_path) -> None:
    assert _manifest_strict_enabled(tmp_path) is False


def test_manifest_strict_returns_true_when_flag_set(tmp_path) -> None:
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n[spec]\nstrict = true\n'
    )
    assert _manifest_strict_enabled(tmp_path) is True


def test_manifest_strict_returns_false_when_flag_unset(tmp_path) -> None:
    (tmp_path / "dazzle.toml").write_text('[project]\nname = "x"\nversion = "0.1.0"\n')
    assert _manifest_strict_enabled(tmp_path) is False


def test_manifest_strict_returns_false_when_flag_explicitly_false(tmp_path) -> None:
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n[spec]\nstrict = false\n'
    )
    assert _manifest_strict_enabled(tmp_path) is False
