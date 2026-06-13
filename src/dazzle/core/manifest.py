from __future__ import annotations  # required: forward reference

import os
import tomllib
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path

from dazzle.core.db_url import normalise_postgres_scheme

_FRAGMENT_CHROME_WARNED = False


def _fragment_chrome_warned() -> bool:
    global _FRAGMENT_CHROME_WARNED
    already = _FRAGMENT_CHROME_WARNED
    _FRAGMENT_CHROME_WARNED = True
    return already


@dataclass
class DockerConfig:
    """Docker infrastructure configuration."""

    variant: str = "compose"  # "compose" or "dockerfile"
    image_name: str | None = None
    base_image: str = "python:3.14-slim"
    port: int = 8000


# =============================================================================
# Shell Configuration
# =============================================================================


@dataclass
class ShellNavConfig:
    """Navigation configuration."""

    style: str = "sidebar"  # "sidebar" | "topbar" | "tabs"
    source: str = "workspaces"  # "workspaces" | "manual"


@dataclass
class ShellFooterLink:
    """A link in the footer."""

    label: str
    href: str


@dataclass
class ShellFooterConfig:
    """Footer configuration."""

    powered_by: bool = True  # Show "Made with Dazzle" link
    links: list[ShellFooterLink] = field(default_factory=list)
    slot: str | None = None  # Optional custom template


@dataclass
class ShellHeaderConfig:
    """Header configuration."""

    show_auth: bool = True  # Show login/logout UI
    slot: str | None = None  # Optional custom template


@dataclass
class ShellPageConfig:
    """Static page configuration."""

    src: str  # Source file (e.g., "pages/privacy.md")
    route: str  # URL route (e.g., "/privacy")
    title: str | None = None  # Page title
    content: str | None = None  # Inline content (markdown or HTML)


@dataclass
class ShellConfig:
    """Shell configuration - app chrome around workspace content."""

    layout: str = "app-shell"  # "app-shell" | "minimal"
    nav: ShellNavConfig = field(default_factory=ShellNavConfig)
    header: ShellHeaderConfig = field(default_factory=ShellHeaderConfig)
    footer: ShellFooterConfig = field(default_factory=ShellFooterConfig)
    pages: list[ShellPageConfig] = field(default_factory=list)


# =============================================================================
# Auth Configuration
# =============================================================================


@dataclass
class AuthSessionConfig:
    """Session-based auth configuration."""

    duration_hours: int = 24
    cookie_name: str = "dazzle_session"
    cookie_secure: bool = True  # Require HTTPS
    cookie_httponly: bool = True  # No JS access


@dataclass
class AuthJwtConfig:
    """JWT auth configuration."""

    access_token_minutes: int = 15
    refresh_token_days: int = 7
    algorithm: str = "HS256"
    # Secret comes from environment: JWT_SECRET


@dataclass
class AuthOAuthProvider:
    """OAuth2 provider configuration."""

    provider: str  # google, github, etc.
    client_id_env: str  # Environment variable name
    client_secret_env: str  # Environment variable name
    scopes: list[str] = field(default_factory=list)


@dataclass
class AuthConfig:
    """Authentication configuration.

    Enable auth by setting enabled=True and choosing a provider.

    Examples in dazzle.toml:

        # Simple session auth (default)
        [auth]
        enabled = true
        provider = "session"

        # JWT auth for APIs
        [auth]
        enabled = true
        provider = "jwt"
        user_entity = "Account"

        # With OAuth2 social login
        [auth]
        enabled = true
        provider = "session"

        [[auth.oauth_providers]]
        provider = "google"
        client_id_env = "GOOGLE_CLIENT_ID"
        client_secret_env = "GOOGLE_CLIENT_SECRET"
        scopes = ["email", "profile"]
    """

    enabled: bool = False
    provider: str = "session"  # "session" | "jwt" | "api_key"
    user_entity: str = "User"  # Name of user entity
    require_email_verification: bool = False
    allow_registration: bool = True
    # auth Plan 1d: opt a single-org app into invisible Phase-2 — login lazily
    # provisions one org + membership per identity (and, for an is_tenant_root
    # app, a matching tenant-root row with the shared id). Default off.
    auto_provision_single_org: bool = False
    # auth Plan 3a: personas allowed to invite / manage org members. Fail-closed —
    # empty means nobody can manage members until the app designates admin roles.
    org_admin_roles: list[str] = field(default_factory=list)
    # Capability -> personas map for the framework's org-admin surfaces. Empty = every capability
    # falls back to org_admin_roles (back-compat). See auth/admin_policy.py CAPABILITIES.
    admin_capabilities: dict[str, list[str]] = field(default_factory=dict)

    # Provider-specific config
    session: AuthSessionConfig = field(default_factory=AuthSessionConfig)
    jwt: AuthJwtConfig = field(default_factory=AuthJwtConfig)

    # OAuth2 providers
    oauth_providers: list[AuthOAuthProvider] = field(default_factory=list)

    # Security settings
    password_min_length: int = 8
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15

    # Audit logging
    audit_enabled: bool = True


@dataclass
class TerraformConfig:
    """Terraform infrastructure configuration."""

    root_module: str = "./infra/terraform"
    cloud_provider: str = "aws"  # "aws", "gcp", "azure"
    environments: list[str] = field(default_factory=lambda: ["dev", "staging", "prod"])
    region: str | None = None


@dataclass
class InfraConfig:
    """Infrastructure configuration from manifest."""

    backends: list[str] = field(default_factory=list)
    docker: DockerConfig = field(default_factory=DockerConfig)
    terraform: TerraformConfig = field(default_factory=TerraformConfig)


# =============================================================================
# Theme Configuration
# =============================================================================


@dataclass
class ThemeConfig:
    """Theme configuration for visual styling.

    Controls the visual appearance of both the app workspace UI and
    public site pages (SiteSpec).

    Available presets:
        - saas-default: Modern SaaS styling with gradient sidebars (default)
        - minimal: Clean, minimal styling with subtle shadows
        - corporate: Professional blue/gray palette for enterprise
        - startup: Bold gradients with vibrant accent colors
        - docs: Documentation-focused, optimized for readability

    Examples in dazzle.toml:

        # Use a preset theme
        [theme]
        preset = "corporate"

        # Override specific tokens
        [theme.colors]
        hero-bg-from = "oklch(0.50 0.18 280)"
        sidebar-from = "oklch(0.30 0.02 200)"

        [theme.spacing]
        section-y = 100
    """

    preset: str = "saas-default"
    colors: dict[str, str] = field(default_factory=dict)
    shadows: dict[str, str] = field(default_factory=dict)
    spacing: dict[str, int] = field(default_factory=dict)
    radii: dict[str, int] = field(default_factory=dict)
    custom: dict[str, str] = field(default_factory=dict)


@dataclass
class StackConfig:
    """Stack configuration - preset combination of backends."""

    name: str
    backends: list[str] = field(default_factory=list)
    description: str | None = None


# =============================================================================
# Dev Configuration (v0.24.0)
# =============================================================================


@dataclass
class URLsConfig:
    """Site and API URL configuration.

    Examples in dazzle.toml:

        [urls]
        site_url = "https://myapp.com"
        api_url = "https://api.myapp.com"
    """

    site_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"


@dataclass
class DatabaseConfig:
    """Database connection configuration.

    Supports direct URLs and environment variable indirection.

    Examples in dazzle.toml:

        # Direct URL (local native)
        [database]
        url = "postgresql://localhost:5432/myapp"

        # Docker (non-default port)
        [database]
        url = "postgresql://localhost:5433/myapp"

        # Env var indirection (safe to commit)
        [database]
        url = "env:DATABASE_URL"
    """

    url: str = "postgresql://localhost:5432/dazzle"


@dataclass
class EnvironmentProfile:
    """Per-environment configuration (database connection, Heroku app)."""

    database_url: str = ""
    database_url_env: str = ""
    heroku_app: str = ""


# =============================================================================
# Dev Configuration (v0.24.0)
# =============================================================================


@dataclass
class DevConfig:
    """Development mode configuration.

    Controls dev-only features like test endpoints.
    These features are automatically disabled when DAZZLE_ENV=production.

    The DAZZLE_ENV environment variable controls the runtime environment:
        - development (default): Test endpoints enabled
        - test: Test endpoints enabled (for E2E tests)
        - production: Disabled for security

    Explicit settings in dazzle.toml override the environment defaults.

    Examples in dazzle.toml:

        # Force-enable test endpoints in production (NOT RECOMMENDED)
        [dev]
        test_endpoints = true

        # Typical production config (usually just use DAZZLE_ENV=production)
        [dev]
        test_endpoints = false
    """

    # None means "use environment default"
    test_endpoints: bool | None = None


@dataclass
class LLMConfig:
    """LLM cognition driver configuration.

    Controls how dev-time agents (``dazzle qa trial``, spec analysis)
    and local ``llm_intent`` testing reach a Claude model:

        - "claude-cli": Claude Code CLI — billed to the developer's
          Claude subscription, no API key. Development only; the
          runtime refuses it under DAZZLE_ENV=production.
        - "anthropic-api": metered Anthropic API (ANTHROPIC_API_KEY).
          Required for deployed apps.
        - "auto" (default when the section is absent): anthropic-api
          if ANTHROPIC_API_KEY is set, else claude-cli if installed.

    Resolution order and the dev → deploy path are documented in
    docs/reference/llm-drivers.md. New projects from ``dazzle init``
    pin "claude-cli" so trying Dazzle never requires API credit.
    """

    driver: str = "auto"  # "auto" | "claude-cli" | "anthropic-api"


@dataclass
class TenantConfig:
    """Multi-tenant configuration.

    isolation = "none" (default): single-schema, no tenant awareness.
    isolation = "schema": each tenant gets a PostgreSQL schema.
    """

    isolation: str = "none"  # "none" | "schema"
    resolver: str = "subdomain"  # "subdomain" | "header" | "session"
    header_name: str = "X-Tenant-ID"  # only used when resolver = "header"
    base_domain: str = ""  # only used when resolver = "subdomain"


@dataclass
class NotificationsConfig:
    """Transactional-notification provider configuration (#952).

    Cycle 2 ships the dataclass + parser; cycle 3+ wires real SMTP /
    SendGrid / SES adapters that consume it. The default ``log``
    provider — used when no ``[notifications]`` block is declared —
    writes every send to the Python logger so adopters can wire
    notifications into their templates and confirm dispatch shape
    before turning on real delivery.

    Attributes:
        provider: Adapter key. ``"log"`` (default) sends to the logger
            only — no network. ``"smtp"`` (cycle 3) talks to an SMTP
            server. ``"sendgrid"`` / ``"ses"`` (cycle 6) hit the
            respective HTTP APIs.
        from_address: Default ``From:`` for outbound email. Per-
            notification ``from:`` overrides land in cycle 3.
        smtp_host / smtp_port / smtp_username / smtp_password: SMTP
            connection details. Empty in the default config; populated
            from ``[notifications.smtp]`` block when ``provider="smtp"``.
        api_key: Provider API token for ``sendgrid``. Empty for
            ``log`` / ``smtp`` / ``ses``.
        aws_region: AWS region for ``ses``. Empty falls back to the
            boto3 default credential chain. Access keys + secrets
            also come from the boto3 chain (env, instance profile,
            AWS_PROFILE) — never declared in dazzle.toml so the
            manifest can be checked into git safely.
    """

    provider: str = "log"  # log | smtp | sendgrid | ses
    from_address: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    api_key: str = ""
    aws_region: str = ""


@dataclass
class I18nConfig:
    """Internationalisation configuration (#955).

    Cycle 1 — locale-resolution scaffolding only. The ``_()`` Jinja filter
    is identity-passthrough until cycle 2 wires gettext catalogues.

    Attributes:
        default_locale: Locale to fall back to when no Accept-Language
            header / cookie / user pref resolves to a supported locale.
            Defaults to ``"en"``.
        supported_locales: Allow-list. The middleware narrows the
            Accept-Language candidates to this set before picking. An
            empty list means "every locale is supported" — useful when
            a project hasn't decided on a translation matrix yet.
        cookie_name: Name of the cookie that carries an explicit user
            override (set by the locale-switcher UI primitive in cycle 6).
    """

    default_locale: str = "en"
    supported_locales: list[str] = field(default_factory=list)
    cookie_name: str = "dazzle_locale"


@dataclass
class CapabilitiesConfig:
    """Opt-in capability declarations (#1342).

    Reads ``[capabilities]`` from dazzle.toml:

        [capabilities]
        enabled = ["auth.enterprise.oidc"]

    Default empty → a greenfield app activates no gated capability.
    """

    enabled: list[str] = field(default_factory=list)


@dataclass
class SpecConfig:
    """Spec-drift guard configuration (#1106 Proposal 3).

    Reads ``[spec]`` from ``dazzle.toml``:

        [spec]
        strict = true   # fail agent loops on undocumented entities

    When ``strict`` is True, ``dazzle spec status --fail-on-strict``
    refuses to pass unless every DSL entity appears as an entity name
    in a row of the ``## Domain map`` table inside ``SPEC.md``. The
    /ship and /improve agent loops invoke this check before commit,
    so an agent that adds an entity without updating the spec index
    can't ship.

    The match is intentionally stricter than the loose substring
    check in ``dazzle spec status`` (which accepts mentions anywhere
    in prose) — table-row presence forces the index-maintenance
    discipline that ``[spec.strict]`` is opting into.
    """

    strict: bool = False


@dataclass
class SigningConfig:
    """Native document signing branding configuration (#1283 phase 8).

    Reads ``[signing]`` from ``dazzle.toml``:

        [signing]
        organisation = "Acme Ltd"
        tagline = "Chartered Accountants"
        footer_text = "Acme Ltd | Registered in England & Wales"
        location = "United Kingdom"

    Wired into ``PdfBranding`` at runtime by ``ServerState`` when
    mounting the signing routes. When unset, the framework falls back
    to ``PdfBranding(organisation=manifest.name)`` so projects that
    declare ``signable: true`` get sensible defaults out of the box.

    The ``location`` field flows into the PKCS#7 signature metadata
    (PdfSignatureMetadata.location), recording the legal jurisdiction
    on every signed PDF.

    Expired-link recovery (TR-53):

        [signing]
        support_contact = "support@acme.example"
        resend_hook = "app.signing.resend.deliver"

    ``resend_hook`` names a project callable
    ``fn(*, entity_name, row, email, signing_url)`` that delivers a
    freshly-minted link to the ORIGINAL recipient via the app's own
    channel — the framework never hands a new token to the browser.
    When set, the expired-link page offers a "Request a new signing
    link" button. ``support_contact`` is shown on signing error pages
    as the human fallback. Both optional; with neither, the expired
    page still tells the signer to contact the sender.
    """

    organisation: str = ""
    tagline: str = ""
    footer_text: str = ""
    location: str = "United Kingdom"
    support_contact: str = ""
    resend_hook: str = ""


@dataclass
class ExtensionsConfig:
    """Registration of project-supplied extensions (closes #786).

    Allows a project's ``dazzle.toml`` to declare FastAPI ``APIRouter``
    objects that the runtime should mount alongside generated routes.
    Each entry is a dotted ``module:attr`` spec imported relative to
    the project root — e.g. ``app.routes.graph:router``.
    """

    routers: list[str] = field(default_factory=list)


@dataclass
class RenderersConfig:
    """Declaration of project-supplied renderer names (closes #1116).

    The DSL's ``render:`` clause on a surface is link-time validated
    against a known-renderer set. The framework ships exactly one
    renderer (``fragment``); projects that register custom renderers
    against the runtime ``RendererRegistry`` must also declare those
    names here so the link-time validator accepts them.

    Example ``dazzle.toml``::

        [renderers]
        extra = ["branch_compare", "cytoscape_graph"]

    The names are merged with the framework defaults at validation
    time via ``dazzle.core.renderer_registry.known_renderer_names``.
    Runtime registration (handler attached to a name) is a separate
    step — done in app code via
    ``services.renderer_registry.register(name=…, handler=…)``.
    See ``fixtures/custom_renderer/`` for a worked example.
    """

    extra: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StorageConfig:
    """One ``[storage.<name>]`` block from ``dazzle.toml`` (#932).

    Storage configs declare a backing store (currently only ``s3``)
    that file fields can bind to via ``field foo: file storage=<name>``.
    The framework's auto-generated upload-ticket / finalize routes
    read this config to build presigned-POST policies and to
    sandbox keys to per-user / per-record prefixes.

    String fields support ``${VAR}`` env-var interpolation. Required
    vars are surfaced via ``dazzle storage env-vars`` and validated
    at app startup.

    Examples in dazzle.toml::

        [storage.cohort_pdfs]
        backend = "s3"
        bucket = "${S3_BUCKET}"
        region = "${AWS_REGION}"
        endpoint_url = "${S3_ENDPOINT_URL}"   # optional — R2/MinIO/LocalStack
        prefix = "production/cohort_assessments/{user_id}/{record_id}/"
        max_bytes = 200_000_000
        content_types = ["application/pdf"]
        ticket_ttl_seconds = 600

    Attributes:
        name: storage identifier (the ``<name>`` in ``[storage.<name>]``).
        backend: storage backend type. v1 supports ``"s3"``.
        bucket: bucket name. May contain ``${VAR}`` references.
        region: AWS region. May contain ``${VAR}`` references.
        endpoint_url: optional S3-compatible endpoint URL. ``None`` =
            real AWS S3. Set to ``${S3_ENDPOINT_URL}`` to support
            MinIO / Cloudflare R2 / LocalStack.
        prefix_template: key prefix with ``{user_id}`` / ``{record_id}``
            substitution. Always ends with ``/``.
        max_bytes: hard limit on uploaded object size (enforced via
            content-length-range condition on the presigned policy).
        content_types: allowlist of acceptable MIME types. Empty list
            means "no content-type restriction".
        ticket_ttl_seconds: how long a minted upload ticket is valid.
    """

    name: str
    backend: str
    bucket: str
    region: str
    prefix_template: str
    max_bytes: int
    content_types: list[str] = field(default_factory=list)
    ticket_ttl_seconds: int = 600
    endpoint_url: str | None = None


@dataclass
class ProjectManifest:
    """
    Project manifest loaded from dazzle.toml.

    Contains project metadata, module paths, and optional infrastructure,
    stack, shell, theme, and authentication configuration.

    Project Types:
        - example: Tutorial/production patterns (default, include in LLM analysis)
        - benchmark: Performance/stress testing (skip unless analyzing performance)
        - test: Test infrastructure projects (skip unless testing)
        - internal: Internal tooling (skip entirely in LLM analysis)
    """

    name: str
    version: str
    project_root: str
    module_paths: list[str]
    project_type: str = "example"  # example | benchmark | test | internal
    infra: InfraConfig | None = None
    stack: StackConfig | None = None
    shell: ShellConfig = field(default_factory=ShellConfig)
    theme: ThemeConfig = field(default_factory=ThemeConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    urls: URLsConfig = field(default_factory=URLsConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    dev: DevConfig = field(default_factory=DevConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    tenant: TenantConfig = field(default_factory=TenantConfig)
    i18n: I18nConfig = field(default_factory=I18nConfig)  # #955
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)  # #952
    spec: SpecConfig = field(default_factory=SpecConfig)  # #1106 Prop 3
    capabilities: CapabilitiesConfig = field(
        default_factory=CapabilitiesConfig
    )  # #1342 opt-in feature gating
    signing: SigningConfig = field(default_factory=SigningConfig)  # #1283 phase 8
    framework_version: str | None = None
    cdn: bool = False  # Local-first; opt-in via [ui] cdn = true in dazzle.toml
    # Asset bundling mode. Resolved at request time by `should_bundle_assets()`:
    #   "auto"   = bundle when DAZZLE_ENV=production, individual scripts in dev (default)
    #   "always" = bundle in every environment (perf testing / staging)
    #   "never"  = individual scripts always (advanced live-reload during prod debugging)
    # Set via `[ui] assets = "always"` in dazzle.toml. CLI flags
    # `dazzle serve --bundle` / `--no-bundle` override per-invocation.
    assets: str = "auto"
    favicon: str | None = None  # Override favicon path; set [ui] favicon = "/static/my-icon.svg"
    dark_mode_toggle: bool = True  # #938 — render the dark/light toggle in
    # the app shell (topbar + sidebar footer) and on marketing pages. Set
    # `[ui] dark_mode_toggle = false` for projects whose brand is
    # deliberately light-only (e.g. paper / academic themes) so the toggle
    # is hidden everywhere AND the server forces `data-theme="light"` on
    # first paint regardless of any stale cookie state.
    app_theme: str | None = None  # v0.61.36: app-shell theme preset (overrides
    # the default shadcn-zinc tokens with an alternate :root block). One of
    # the presets shipped in src/dazzle/ui/runtime/static/css/themes/<name>.css
    # — e.g. "linear-dark", "paper", "stripe". None = default theme.
    # Distinct from [theme] which covers site/marketing-page tokens.
    haptic: bool = False  # #958 cycle 5 — haptic opt-in. When True, the
    # framework JS calls `navigator.vibrate(...)` on key actions (toast
    # success, swipe, pull-to-refresh complete, confirm submit) on
    # mobile devices that support the Vibration API. Off by default so
    # adopters consciously opt in — uninvited vibration is jarring.
    # Phase 4 app-shell migration (v0.67.45): the `fragment_chrome`
    # flag is retired. Typed-Fragment is the only render path now.
    # Backward-compat aliases keep accepting `[ui] fragment_chrome =
    # true` in dazzle.toml without raising — the loader logs a
    # deprecation notice but does NOT toggle anything.
    environments: dict[str, EnvironmentProfile] = field(default_factory=dict)
    extensions: ExtensionsConfig = field(default_factory=ExtensionsConfig)
    # v0.71.x #1116 — project-side renderer-name allowlist. Merged with
    # framework defaults via known_renderer_names() for link-time validation.
    renderers: RenderersConfig = field(default_factory=RenderersConfig)
    # v0.61.104 (#932): per-name `[storage.<name>]` blocks. Keyed by the
    # storage name. Empty when no storage blocks are declared.
    storage_defs: dict[str, StorageConfig] = field(default_factory=dict)
    # v0.71.140 (#1206): audit-log tamper-evidence opt-in shipped in #1197.
    # Read from `[audit] integrity = "<mode>"` in dazzle.toml. Threaded
    # through `create_app_factory()` → `build_server_config()` →
    # `ServerConfig.audit_integrity` → `AuditLogger(audit_integrity=...)`.
    # "none" (default) leaves the schema and write path byte-identical to
    # pre-#1197 behaviour; "hash_chain" enables the per-row sha256 chain.
    audit_integrity: str = "none"  # "none" | "hash_chain"


_AUDIT_INTEGRITY_VALID = {"none", "hash_chain"}

_STORAGE_VALID_BACKENDS = {"s3"}


def _parse_storage_configs(data: dict[str, object]) -> dict[str, StorageConfig]:
    """Parse ``[storage.<name>]`` blocks from manifest TOML data (#932).

    Validates required keys + backend allowlist. Raises a clear
    ``ValueError`` if a block is malformed; the caller wraps that in a
    project-load error so authors see one diagnostic per cycle, not a
    Pydantic stack trace.
    """
    raw = data.get("storage") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, StorageConfig] = {}
    for name, block in raw.items():
        if not isinstance(block, dict):
            raise ValueError(f"[storage.{name}] must be a TOML table")
        backend = str(block.get("backend") or "")
        if backend not in _STORAGE_VALID_BACKENDS:
            raise ValueError(
                f"[storage.{name}] backend must be one of "
                f"{sorted(_STORAGE_VALID_BACKENDS)!r}, got {backend!r}"
            )
        for required in ("bucket", "region", "prefix"):
            if not block.get(required):
                raise ValueError(f"[storage.{name}] missing required key {required!r}")
        prefix_template = str(block["prefix"])
        if not prefix_template.endswith("/"):
            prefix_template = prefix_template + "/"
        max_bytes = int(block.get("max_bytes", 50 * 1024 * 1024))  # 50 MB default
        ticket_ttl = int(block.get("ticket_ttl_seconds", 600))
        content_types = list(block.get("content_types") or [])
        out[name] = StorageConfig(
            name=name,
            backend=backend,
            bucket=str(block["bucket"]),
            region=str(block["region"]),
            prefix_template=prefix_template,
            max_bytes=max_bytes,
            content_types=content_types,
            ticket_ttl_seconds=ticket_ttl,
            endpoint_url=str(block["endpoint_url"]) if block.get("endpoint_url") else None,
        )
    return out


def check_framework_version(manifest: ProjectManifest) -> None:
    """Raise SystemExit if installed version doesn't satisfy constraint."""
    if not manifest.framework_version:
        return
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    installed = Version(version("dazzle-dsl"))
    constraint = manifest.framework_version
    # Handle tilde shorthand: "~0.38" → ">=0.38,<0.39"
    if constraint.startswith("~"):
        base = constraint[1:]
        parts = base.split(".")
        if len(parts) >= 2:
            upper = f"{int(parts[0])}.{int(parts[1]) + 1}"
        else:
            upper = f"{int(parts[0]) + 1}"
        spec = SpecifierSet(f">={base},<{upper}")
    else:
        spec = SpecifierSet(constraint)
    if installed not in spec:
        raise SystemExit(
            f"Framework version mismatch: installed {installed}, "
            f"project requires {constraint}. "
            f"Run: pip install 'dazzle-dsl{constraint}'"
        )


def load_manifest(path: Path) -> ProjectManifest:
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    project = data.get("project", {})
    modules = data.get("modules", {})
    infra_data = data.get("infra", {})
    stack_data = data.get("stack", {})

    # Parse infra config if present
    infra_config = None
    if infra_data:
        docker_data = infra_data.get("docker", {})
        terraform_data = infra_data.get("terraform", {})

        docker_config = DockerConfig(
            variant=docker_data.get("variant", "compose"),
            image_name=docker_data.get("image_name"),
            base_image=docker_data.get("base_image", "python:3.14-slim"),
            port=docker_data.get("port", 8000),
        )

        terraform_config = TerraformConfig(
            root_module=terraform_data.get("root_module", "./infra/terraform"),
            cloud_provider=terraform_data.get("cloud_provider", "aws"),
            environments=terraform_data.get("environments", ["dev", "staging", "prod"]),
            region=terraform_data.get("region"),
        )

        infra_config = InfraConfig(
            backends=infra_data.get("backends", []),
            docker=docker_config,
            terraform=terraform_config,
        )

    # Parse stack config if present
    stack_config = None
    if stack_data:
        stack_config = StackConfig(
            name=stack_data.get("name", ""),
            backends=stack_data.get("backends", []),
            description=stack_data.get("description"),
        )

    # Parse shell config (with sensible defaults)
    shell_data = data.get("shell", {})
    nav_data = shell_data.get("nav", {})
    header_data = shell_data.get("header", {})
    footer_data = shell_data.get("footer", {})
    pages_data = shell_data.get("pages", [])

    nav_config = ShellNavConfig(
        style=nav_data.get("style", "sidebar"),
        source=nav_data.get("source", "workspaces"),
    )

    header_config = ShellHeaderConfig(
        show_auth=header_data.get("show_auth", True),
        slot=header_data.get("slot"),
    )

    footer_links = [
        ShellFooterLink(label=link.get("label", ""), href=link.get("href", ""))
        for link in footer_data.get("links", [])
    ]

    footer_config = ShellFooterConfig(
        powered_by=footer_data.get("powered_by", True),
        links=footer_links,
        slot=footer_data.get("slot"),
    )

    pages_config = [
        ShellPageConfig(
            src=page.get("src", ""),
            route=page.get("route", ""),
            title=page.get("title"),
            content=page.get("content"),
        )
        for page in pages_data
    ]

    shell_config = ShellConfig(
        layout=shell_data.get("layout", "app-shell"),
        nav=nav_config,
        header=header_config,
        footer=footer_config,
        pages=pages_config,
    )

    # Parse theme config (v0.16.0)
    theme_data = data.get("theme", {})
    theme_config = ThemeConfig(
        preset=theme_data.get("preset", "saas-default"),
        colors=theme_data.get("colors", {}),
        shadows=theme_data.get("shadows", {}),
        spacing=theme_data.get("spacing", {}),
        radii=theme_data.get("radii", {}),
        custom=theme_data.get("custom", {}),
    )

    # Parse auth config
    auth_data = data.get("auth", {})
    session_data = auth_data.get("session", {})
    jwt_data = auth_data.get("jwt", {})
    oauth_providers_data = auth_data.get("oauth_providers", [])

    session_config = AuthSessionConfig(
        duration_hours=session_data.get("duration_hours", 24),
        cookie_name=session_data.get("cookie_name", "dazzle_session"),
        cookie_secure=session_data.get("cookie_secure", True),
        cookie_httponly=session_data.get("cookie_httponly", True),
    )

    jwt_config = AuthJwtConfig(
        access_token_minutes=jwt_data.get("access_token_minutes", 15),
        refresh_token_days=jwt_data.get("refresh_token_days", 7),
        algorithm=jwt_data.get("algorithm", "HS256"),
    )

    oauth_providers = [
        AuthOAuthProvider(
            provider=provider.get("provider", ""),
            client_id_env=provider.get("client_id_env", ""),
            client_secret_env=provider.get("client_secret_env", ""),
            scopes=provider.get("scopes", []),
        )
        for provider in oauth_providers_data
    ]

    auth_config = AuthConfig(
        enabled=auth_data.get("enabled", False),
        provider=auth_data.get("provider", "session"),
        user_entity=auth_data.get("user_entity", "User"),
        require_email_verification=auth_data.get("require_email_verification", False),
        allow_registration=auth_data.get("allow_registration", True),
        org_admin_roles=list(auth_data.get("org_admin_roles", [])),
        admin_capabilities={
            str(k): [str(r) for r in (v or [])]
            for k, v in (auth_data.get("admin_capabilities", {}) or {}).items()
        },
        session=session_config,
        jwt=jwt_config,
        oauth_providers=oauth_providers,
        password_min_length=auth_data.get("password_min_length", 8),
        max_login_attempts=auth_data.get("max_login_attempts", 5),
        lockout_duration_minutes=auth_data.get("lockout_duration_minutes", 15),
        audit_enabled=auth_data.get("audit_enabled", True),
    )

    # Parse database config
    db_data = data.get("database", {})
    database_config = DatabaseConfig(
        url=db_data.get("url", "postgresql://localhost:5432/dazzle"),
    )

    # Parse dev config (v0.24.0)
    dev_data = data.get("dev", {})
    dev_config = DevConfig(
        test_endpoints=dev_data.get("test_endpoints"),  # None if not set
    )

    # Parse LLM driver config
    llm_data = data.get("llm", {})
    llm_config = LLMConfig(
        driver=llm_data.get("driver", "auto"),
    )

    # Parse tenant config
    tenant_data = data.get("tenant", {})
    tenant_config = TenantConfig(
        isolation=tenant_data.get("isolation", "none"),
        resolver=tenant_data.get("resolver", "subdomain"),
        header_name=tenant_data.get("header_name", "X-Tenant-ID"),
        base_domain=tenant_data.get("base_domain", ""),
    )

    # Parse i18n config (#955)
    i18n_data = data.get("i18n", {}) if isinstance(data.get("i18n"), dict) else {}
    raw_supported = i18n_data.get("supported", [])
    if not isinstance(raw_supported, list):
        raw_supported = []
    i18n_config = I18nConfig(
        default_locale=str(i18n_data.get("default", "en")),
        supported_locales=[str(loc) for loc in raw_supported if isinstance(loc, str)],
        cookie_name=str(i18n_data.get("cookie_name", "dazzle_locale")),
    )

    # Parse [notifications] config (#952). Allows nested [notifications.smtp]
    # so SMTP credentials live in a dedicated subtable rather than
    # cluttering the top level.
    notif_data = (
        data.get("notifications", {}) if isinstance(data.get("notifications"), dict) else {}
    )
    smtp_data = notif_data.get("smtp", {}) if isinstance(notif_data.get("smtp"), dict) else {}
    valid_providers = {"log", "smtp", "sendgrid", "ses"}
    provider = str(notif_data.get("provider", "log")).lower()
    if provider not in valid_providers:
        raise ValueError(
            f"[notifications] provider must be one of {sorted(valid_providers)!r}; got {provider!r}"
        )
    notifications_config = NotificationsConfig(
        provider=provider,
        from_address=str(notif_data.get("from", "") or notif_data.get("from_address", "")),
        smtp_host=str(smtp_data.get("host", "")),
        smtp_port=int(smtp_data.get("port", 587)),
        smtp_username=str(smtp_data.get("username", "")),
        smtp_password=str(smtp_data.get("password", "")),
        api_key=str(notif_data.get("api_key", "")),
        aws_region=str(notif_data.get("aws_region", "")),
    )

    # Parse URLs config
    urls_data = data.get("urls", {})
    urls_config = URLsConfig(
        site_url=urls_data.get("site_url", "http://localhost:3000"),
        api_url=urls_data.get("api_url", "http://localhost:8000"),
    )

    # Parse [ui] config
    ui_data = data.get("ui", {})
    cdn_enabled = ui_data.get("cdn", False)
    favicon_path = ui_data.get("favicon")
    app_theme_name = ui_data.get("theme") or ui_data.get("app_theme")
    dark_mode_toggle_enabled = bool(ui_data.get("dark_mode_toggle", True))
    haptic_enabled = bool(ui_data.get("haptic", False))
    # Phase 4 app-shell migration (v0.67.45): `[ui] fragment_chrome` is
    # retired. The key is still accepted in dazzle.toml without raising
    # so existing project manifests keep loading; a deprecation log
    # surfaces the no-op. Dedupe via module-level guard: load_manifest is
    # called 3× per boot (manifest, appspec loader, extensions router).
    if "fragment_chrome" in ui_data and not _fragment_chrome_warned():
        import logging as _logging

        _logging.getLogger("dazzle.manifest").info(
            "[ui] fragment_chrome is deprecated and ignored — typed-Fragment "
            "is the only render path since v0.67.43. Remove the key from "
            "dazzle.toml."
        )
    assets_mode = ui_data.get("assets", "auto")
    if assets_mode not in ("auto", "always", "never"):
        raise ValueError(f"[ui] assets must be 'auto', 'always', or 'never'; got {assets_mode!r}")

    # Parse [extensions] section (#786)
    extensions_data = data.get("extensions", {})
    raw_routers = extensions_data.get("routers", [])
    if not isinstance(raw_routers, list):
        raw_routers = []
    extensions_config = ExtensionsConfig(
        routers=[str(r) for r in raw_routers if isinstance(r, str)],
    )

    # Parse [renderers] section (#1116) — project-side renderer-name
    # allowlist for the DSL's `render:` clause.
    renderers_data = data.get("renderers", {})
    raw_renderer_extra = renderers_data.get("extra", []) if isinstance(renderers_data, dict) else []
    if not isinstance(raw_renderer_extra, list):
        raw_renderer_extra = []
    renderers_config = RenderersConfig(
        extra=[str(r) for r in raw_renderer_extra if isinstance(r, str)],
    )

    # Parse environment profiles
    env_data = data.get("environments", {})
    environments: dict[str, EnvironmentProfile] = {}
    for env_name, env_config in env_data.items():
        if isinstance(env_config, dict):
            environments[env_name] = EnvironmentProfile(
                database_url=env_config.get("database_url", ""),
                database_url_env=env_config.get("database_url_env", ""),
                heroku_app=env_config.get("heroku_app", ""),
            )

    # Parse [storage.<name>] blocks (v0.61.104, #932)
    storage_defs = _parse_storage_configs(data)

    # Parse [audit] block (#1206) — opt-in tamper-evidence shipped in #1197.
    audit_data = data.get("audit", {}) if isinstance(data.get("audit"), dict) else {}
    audit_integrity = str(audit_data.get("integrity", "none"))
    if audit_integrity not in _AUDIT_INTEGRITY_VALID:
        raise ValueError(
            f"[audit] integrity must be one of {sorted(_AUDIT_INTEGRITY_VALID)!r}; "
            f"got {audit_integrity!r}"
        )

    # Parse [spec] block (#1106 Prop 3)
    spec_data = data.get("spec", {}) if isinstance(data.get("spec"), dict) else {}
    spec_config = SpecConfig(strict=bool(spec_data.get("strict", False)))

    # Parse [capabilities] block (#1342 opt-in feature gating)
    cap_data = data.get("capabilities", {}) if isinstance(data.get("capabilities"), dict) else {}
    raw_enabled = cap_data.get("enabled", [])
    if not isinstance(raw_enabled, list):
        # Fail loud, not open: a scalar (e.g. enabled = "auth.enterprise.oidc")
        # would otherwise shred into characters and silently activate nothing.
        raise ValueError(
            "[capabilities] enabled must be a list of capability ids, "
            f"got {type(raw_enabled).__name__}"
        )
    capabilities_config = CapabilitiesConfig(enabled=[str(x) for x in raw_enabled])

    # Parse [signing] block (#1283 phase 8 — PdfBranding wire-up)
    signing_data = data.get("signing", {}) if isinstance(data.get("signing"), dict) else {}
    signing_config = SigningConfig(
        organisation=str(signing_data.get("organisation", "")),
        tagline=str(signing_data.get("tagline", "")),
        footer_text=str(signing_data.get("footer_text", "")),
        location=str(signing_data.get("location", "United Kingdom")),
        support_contact=str(signing_data.get("support_contact", "")),
        resend_hook=str(signing_data.get("resend_hook", "")),
    )

    return ProjectManifest(
        name=project.get("name", "unnamed"),
        version=project.get("version", "0.0.0"),
        project_root=project.get("root", ""),
        module_paths=modules.get("paths", ["./dsl"]),
        project_type=project.get("type", "example"),
        infra=infra_config,
        stack=stack_config,
        shell=shell_config,
        theme=theme_config,
        auth=auth_config,
        urls=urls_config,
        database=database_config,
        dev=dev_config,
        llm=llm_config,
        tenant=tenant_config,
        i18n=i18n_config,
        notifications=notifications_config,
        spec=spec_config,
        capabilities=capabilities_config,
        signing=signing_config,
        framework_version=project.get("framework_version"),
        cdn=cdn_enabled,
        assets=assets_mode,
        favicon=favicon_path,
        app_theme=app_theme_name,
        dark_mode_toggle=dark_mode_toggle_enabled,
        haptic=haptic_enabled,
        environments=environments,
        extensions=extensions_config,
        renderers=renderers_config,
        storage_defs=storage_defs,
        audit_integrity=audit_integrity,
    )


_DEFAULT_DATABASE_URL = "postgresql://localhost:5432/dazzle"


def resolve_database_url(
    manifest: ProjectManifest | None = None,
    *,
    explicit_url: str = "",
    env_name: str = "",
) -> str:
    """Resolve the database URL with clear priority.

    Priority:
        1. explicit_url (CLI ``--database-url`` flag)
        2. Environment profile (``--env`` / ``DAZZLE_ENV``)
        3. ``DATABASE_URL`` environment variable
        4. ``dazzle.toml`` ``[database].url`` (supports ``env:VAR_NAME`` indirection)
        5. Default: ``postgresql://localhost:5432/dazzle``

    The ``env:VAR_NAME`` syntax in the manifest lets users commit a safe pointer
    (e.g. ``url = "env:DATABASE_URL"``) that resolves at runtime.

    Heroku-style ``postgres://`` URLs are normalised to ``postgresql://``
    for SQLAlchemy compatibility.
    """
    # 1. Explicit CLI flag
    if explicit_url:
        return normalise_postgres_scheme(explicit_url)

    # 2. Environment profile
    if env_name and manifest is not None:
        if env_name not in manifest.environments:
            available = ", ".join(sorted(manifest.environments.keys())) or "(none)"
            raise SystemExit(
                f"Unknown environment '{env_name}'. "
                f"Available: {available}. "
                f"Check [environments.*] in dazzle.toml."
            )
        profile = manifest.environments[env_name]
        # database_url wins over database_url_env on the same profile
        if profile.database_url:
            return normalise_postgres_scheme(profile.database_url)
        if profile.database_url_env:
            resolved = os.environ.get(profile.database_url_env, "")
            if resolved:
                return normalise_postgres_scheme(resolved)
        # Profile set but neither field resolved — fall through

    # 3. Environment variable
    env_url = os.environ.get("DATABASE_URL", "")
    if env_url:
        return normalise_postgres_scheme(env_url)

    # 4. Manifest [database].url
    if manifest is not None:
        manifest_url = manifest.database.url
        if manifest_url.startswith("env:"):
            var_name = manifest_url[4:]
            resolved = os.environ.get(var_name, "")
            if resolved:
                return normalise_postgres_scheme(resolved)
            # env var not set — fall through to default
        elif manifest_url and manifest_url != _DEFAULT_DATABASE_URL:
            return normalise_postgres_scheme(manifest_url)

    # 5. Default
    return _DEFAULT_DATABASE_URL


_DEFAULT_SITE_URL = "http://localhost:3000"
_DEFAULT_API_URL = "http://localhost:8000"


def resolve_site_url(manifest: ProjectManifest | None = None) -> str:
    """Resolve the site (frontend) URL.

    Priority:
        1. ``DAZZLE_SITE_URL`` environment variable
        2. ``dazzle.toml`` ``[urls].site_url``
        3. Default: ``http://localhost:3000``
    """
    env_url = os.environ.get("DAZZLE_SITE_URL", "")
    if env_url:
        return env_url.rstrip("/")

    if manifest is not None and manifest.urls.site_url != _DEFAULT_SITE_URL:
        return manifest.urls.site_url.rstrip("/")

    return _DEFAULT_SITE_URL


def resolve_api_url(manifest: ProjectManifest | None = None) -> str:
    """Resolve the API (backend) URL.

    Priority:
        1. ``DAZZLE_API_URL`` environment variable
        2. ``dazzle.toml`` ``[urls].api_url``
        3. Default: ``http://localhost:8000``
    """
    env_url = os.environ.get("DAZZLE_API_URL", "")
    if env_url:
        return env_url.rstrip("/")

    if manifest is not None and manifest.urls.api_url != _DEFAULT_API_URL:
        return manifest.urls.api_url.rstrip("/")

    return _DEFAULT_API_URL
