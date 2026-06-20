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

import re

from dazzle.http.runtime.csrf import CSRFConfig, configure_csrf_for_profile


class TestDefaultExemptListPreserved:
    def test_known_defaults_present(self) -> None:
        """Sanity-check: the framework's default exempt entries are still
        present after the #1212 refactor."""
        config = CSRFConfig()
        # A handful of stable defaults from src/dazzle/http/runtime/csrf.py.
        for exact in ("/health", "/docs", "/_dazzle/consent"):
            assert exact in config.exempt_paths, exact
        for prefix in ("/auth/", "/_dazzle/i18n/"):
            assert prefix in config.exempt_path_prefixes, prefix
        # /webhooks/ moved to na_signature_prefixes (NA_SIGNATURE disposition,
        # declarative-CSRF Phase 3) — same value, new field.
        assert "/webhooks/" in config.na_signature_prefixes

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


class TestSigningExemptNarrowed:
    """#1284: the signing-route CSRF exemption must match ONLY the exact
    two-segment route shape, not a broad ``/api/sign/`` prefix. A future route
    accidentally mounted deeper under that prefix (e.g. an admin endpoint) must
    fall back to normal CSRF validation rather than silently inherit the
    exemption.
    """

    def _matches_any_exempt(self, config: CSRFConfig, path: str) -> bool:
        """Mirror the middleware's exemption logic for a state-changing path:
        exact paths, prefixes, then anchored regexes. Since declarative-CSRF
        Phase 3 the signing routes derive NA_SIGNATURE from
        ``na_signature_prefixes`` / ``na_signature_regexes`` rather than the
        generic exempt lists, so they are consulted here too."""
        if path in config.exempt_paths:
            return True
        if any(path.startswith(p) for p in config.exempt_path_prefixes):
            return True
        if any(path.startswith(p) for p in config.na_signature_prefixes):
            return True
        return any(re.fullmatch(p, path) for p in config.na_signature_regexes)

    def test_no_broad_sign_prefix_remains(self) -> None:
        config = CSRFConfig()
        # The broad startswith prefixes that #1284 was opened to remove must
        # be gone — replaced by anchored regexes.
        assert "/sign/" not in config.exempt_path_prefixes
        assert "/api/sign/" not in config.exempt_path_prefixes

    def test_legitimate_signing_routes_exempt(self) -> None:
        config = CSRFConfig()
        uuid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
        for path in (
            f"/sign/contract/{uuid}",
            f"/api/sign/contract/{uuid}",
            # entity_name is an opaque single segment; the record_id tail is
            # anchored to a UUID, matching the route's ``record_id: UUID``.
            f"/sign/letter/{uuid}",
            f"/api/sign/letter/{uuid}",
            # Pydantic's UUID validator accepts the 32-char no-hyphen spelling,
            # so it is a reachable signing route and must stay exempt too.
            f"/sign/contract/{uuid.replace('-', '')}",
            f"/api/sign/contract/{uuid.replace('-', '')}",
        ):
            assert self._matches_any_exempt(config, path), path

    def test_deeper_nested_routes_not_exempt(self) -> None:
        config = CSRFConfig()
        uuid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
        # The core #1284 anti-regression: a hypothetical admin route mounted
        # under the prefix must NOT be exempt — including a two-segment route
        # whose tail is not a UUID.
        for path in (
            "/api/sign/admin/revoke-all",
            f"/api/sign/contract/{uuid}/delete",
            "/sign/admin/purge",
            f"/sign/contract/{uuid}/extra",
        ):
            assert not self._matches_any_exempt(config, path), path

    def test_non_uuid_tail_not_exempt(self) -> None:
        config = CSRFConfig()
        # The record_id tail must be a UUID — a free-word tail is unreachable
        # on the real route (FastAPI 422s it) and must not be exempt either.
        for path in (
            "/api/sign/letter/abc",
            "/sign/letter/abc",
            "/api/sign/admin/dashboard",
        ):
            assert not self._matches_any_exempt(config, path), path

    def test_partial_and_sibling_paths_not_exempt(self) -> None:
        config = CSRFConfig()
        uuid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
        # The bare prefix, missing segments, or a same-stem sibling must not
        # match the anchored pattern.
        for path in (
            "/api/sign/",
            "/api/sign/contract",
            "/sign/",
            "/sign/contract",
            f"/api/signups/contract/{uuid}",
            f"/signatures/contract/{uuid}",
        ):
            assert not self._matches_any_exempt(config, path), path
