"""CSRF exempt-path extension contract (#1212).

Downstream apps that need to register internal POST endpoints as CSRF-exempt
(e.g. a public-read GraphQL gateway already authenticated by Bearer) used to
rely on mutating ``app.state.csrf_config.exempt_paths`` after framework boot,
which is an implementation detail. The public knob is the ``extra_exempt_paths``
parameter on ``configure_csrf_for_profile`` / ``apply_csrf_protection``, fed by
``ServerConfig.csrf_exempt_paths``.

The central anti-regression for the issue's root concern: ``POST /graphql`` is
NOT in the default exempt list. GraphQL POSTs include mutations and must carry
``X-CSRF-Token`` like every other state-changing request.
"""

from __future__ import annotations

from dazzle.back.runtime.csrf import CSRFConfig, configure_csrf_for_profile


class TestDefaultExemptListPreserved:
    def test_known_defaults_present(self) -> None:
        """Sanity-check: the framework's default exempt entries are still
        present after the #1212 refactor."""
        config = CSRFConfig()
        # A handful of stable defaults from src/dazzle/back/runtime/csrf.py.
        for exact in ("/health", "/docs", "/_dazzle/consent"):
            assert exact in config.exempt_paths, exact
        for prefix in ("/auth/", "/webhooks/", "/_dazzle/i18n/"):
            assert prefix in config.exempt_path_prefixes, prefix

    def test_configure_with_no_extras_matches_default(self) -> None:
        default = CSRFConfig()
        built = configure_csrf_for_profile("standard")
        # The configured one is enabled; the default dataclass is not. The
        # exempt_paths content should otherwise match exactly.
        assert built.exempt_paths == default.exempt_paths
        assert built.enabled is True


class TestExtrasAreAppended:
    def test_extras_appended_to_defaults(self) -> None:
        built = configure_csrf_for_profile(
            "standard",
            extra_exempt_paths=["/my-webhook", "/integrations/stripe"],
        )
        assert "/my-webhook" in built.exempt_paths
        assert "/integrations/stripe" in built.exempt_paths
        # Defaults still present.
        assert "/health" in built.exempt_paths
        assert "/_dazzle/consent" in built.exempt_paths


class TestNoDuplicates:
    def test_extra_already_in_defaults_is_not_doubled(self) -> None:
        # `/health` is in the default exempt_paths list — passing it as an
        # extra must not produce a duplicate entry.
        built = configure_csrf_for_profile("standard", extra_exempt_paths=["/health"])
        assert built.exempt_paths.count("/health") == 1


class TestGraphQLNotExempt:
    """The central anti-regression for #1212: GraphQL POSTs require a CSRF
    token because mutations are state-changing. ``/graphql`` must not be in
    the default exempt list under any profile."""

    def test_graphql_not_in_default_exact_paths(self) -> None:
        config = CSRFConfig()
        assert "/graphql" not in config.exempt_paths

    def test_graphql_not_in_default_prefixes(self) -> None:
        config = CSRFConfig()
        # No prefix-form match either (e.g. `/graph` would catch `/graphql`).
        for prefix in config.exempt_path_prefixes:
            assert not "/graphql".startswith(prefix), (
                f"prefix {prefix!r} would silently exempt /graphql"
            )

    def test_graphql_not_in_configured_paths(self) -> None:
        built = configure_csrf_for_profile("standard")
        assert "/graphql" not in built.exempt_paths
