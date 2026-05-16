"""Tests for ``dazzle spec status`` — narrative-spec ↔ DSL drift (#1106 Prop 1)."""

from types import SimpleNamespace

from dazzle.cli.spec import (
    _compute_drift,
    _extract_entity_candidates,
    _format_report,
    _spec_mentions_entity,
)


def _fake_appspec(*entity_names: str) -> object:
    """Build a minimal AppSpec-shaped namespace with the named entities."""
    entities = [SimpleNamespace(name=n) for n in entity_names]
    return SimpleNamespace(domain=SimpleNamespace(entities=entities))


def test_spec_mentions_entity_matches_singular_and_plural() -> None:
    text = "the system tracks every order and the user can view orders".lower()
    assert _spec_mentions_entity("Order", text) is True
    assert _spec_mentions_entity("User", text) is True
    # Entity not present anywhere
    assert _spec_mentions_entity("Invoice", text) is False


def test_spec_mentions_entity_does_not_partial_match() -> None:
    """`user` must not match `username` — word boundary required."""
    text = "stores the username and the user-agent string".lower()
    # `user` IS present as a whole word, so this matches.
    assert _spec_mentions_entity("User", text) is True
    # `name` is NOT a whole word here — only `username`.
    text2 = "the username only".lower()
    assert _spec_mentions_entity("Name", text2) is False


def test_extract_entity_candidates_filters_header_only_tokens() -> None:
    """Tokens only in headers don't count — they're structural, not entity refs."""
    spec = "# Overview\n# Order\n\nThe system tracks invoices."
    candidates = _extract_entity_candidates(spec)
    # `Overview` filtered by both `header_only` and `_NON_ENTITY_TITLECASE`.
    # `Order` is header-only AND not in body → filtered.
    # Invoices is TitleCase-ish? "Invoices" — let's check.
    # Actually 'Invoices' starts with capital, regex match.
    # Plural form survives because we no longer naive-singularise.
    assert "Overview" not in candidates
    assert "Order" not in candidates  # header-only


def test_extract_entity_candidates_skips_non_entity_words() -> None:
    """Common prose TitleCase tokens are filtered (System, Platform, dates)."""
    spec = "The System runs on every Monday in January. Configure the Workflow."
    candidates = _extract_entity_candidates(spec)
    assert "System" not in candidates
    assert "Monday" not in candidates
    assert "January" not in candidates
    assert "Configure" not in candidates


def test_compute_drift_with_no_spec_marks_spec_absent() -> None:
    appspec = _fake_appspec("Order", "User")
    report = _compute_drift(appspec, "", spec_present=False)  # type: ignore[arg-type]
    assert report.spec_present is False
    # No spec to compare against → no candidates flagged.
    assert report.missing_from_dsl == []
    # And no missing_from_spec since the spec is absent (every entity
    # would naively be "missing" — but the renderer special-cases the
    # absent state). The compute function still reports them honestly:
    assert sorted(report.missing_from_spec) == ["Order", "User"]


def test_compute_drift_finds_entities_missing_from_spec() -> None:
    """DSL has 3 entities; the spec only mentions 2."""
    appspec = _fake_appspec("Order", "User", "Invoice")
    spec = "Users place Orders. Orders are tracked."
    report = _compute_drift(appspec, spec, spec_present=True)  # type: ignore[arg-type]
    assert report.missing_from_spec == ["Invoice"]


def test_compute_drift_finds_candidates_missing_from_dsl() -> None:
    """The spec mentions an entity-shaped noun the DSL doesn't model."""
    appspec = _fake_appspec("Order")
    spec = "Orders are placed by Customers. Each Order has a Shipment."
    report = _compute_drift(appspec, spec, spec_present=True)  # type: ignore[arg-type]
    # `Customer` and `Shipment` aren't in the DSL.
    assert "Customer" in report.missing_from_dsl or "Customers" in report.missing_from_dsl
    assert "Shipment" in report.missing_from_dsl


def test_compute_drift_filters_framework_injected_entities_by_default() -> None:
    """AIJob / DeployHistory / FeedbackReport / SystemHealth / SystemMetric
    are framework-injected on every project. They don't need spec coverage."""
    appspec = _fake_appspec(
        "Order", "AIJob", "DeployHistory", "FeedbackReport", "SystemHealth", "SystemMetric"
    )
    report = _compute_drift(appspec, "Orders are placed.", spec_present=True)  # type: ignore[arg-type]
    # Only Order is checked; framework entities are stripped.
    assert "AIJob" not in report.missing_from_spec
    assert "DeployHistory" not in report.missing_from_spec
    assert report.missing_from_spec == []


def test_compute_drift_includes_framework_entities_when_opt_in() -> None:
    appspec = _fake_appspec("Order", "AIJob")
    report = _compute_drift(
        appspec, "Orders are placed.", spec_present=True, include_framework_entities=True
    )  # type: ignore[arg-type]
    # With the opt-in, AIJob shows up as missing.
    assert "AIJob" in report.missing_from_spec


def test_format_report_friendly_when_no_drift() -> None:
    appspec = _fake_appspec("Order")
    report = _compute_drift(appspec, "Orders are placed.", spec_present=True)  # type: ignore[arg-type]
    out = _format_report(report)
    assert "DSL entities: 1" in out
    assert "Missing from spec (0)" in out
    assert "(none — every DSL entity is mentioned in the spec)" in out


def test_format_report_caps_missing_from_dsl_at_30() -> None:
    """Heuristic candidate list is capped to keep the report scannable."""
    appspec = _fake_appspec("Order")
    # Use 35 distinct CamelCase nouns so each survives the regex
    # (`[A-Z][a-z]+(?:[A-Z][a-z]+)*`) and the false-positive filter.
    bases = [
        "Alpha",
        "Bravo",
        "Charlie",
        "Delta",
        "Echo",
        "Foxtrot",
        "Golf",
        "Hotel",
        "India",
        "Juliet",
        "Kilo",
        "Lima",
        "Mike",
        "November",
        "Oscar",
        "Papa",
        "Quebec",
        "Romeo",
        "Sierra",
        "Tango",
        "Uniform",
        "Victor",
        "Whiskey",
        "Xray",
        "Yankee",
        "Zulu",
        "Alfa",
        "Beta",
        "Gamma",
        "Epsilon",
        "Zeta",
        "Eta",
        "Theta",
        "Iota",
        "Kappa",
    ]
    spec = "Orders. " + " ".join(f"the {b}Widget" for b in bases)
    report = _compute_drift(appspec, spec, spec_present=True)  # type: ignore[arg-type]
    out = _format_report(report)
    assert len(report.missing_from_dsl) > 30
    assert "more (extend the skip list" in out
