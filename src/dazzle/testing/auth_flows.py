"""
Auth Flow Templates for E2E Testing.

Generates authentication-related test flows:
- Login with valid credentials
- Login with invalid credentials
- Logout
- Registration (if enabled)
- Protected route access
- Persona-based access control
"""

from dazzle.core.ir import (
    FixtureSpec,
    FlowAssertion,
    FlowAssertionKind,
    FlowPrecondition,
    FlowPriority,
    FlowSpec,
    FlowStep,
    FlowStepKind,
    SurfaceAccessSpec,
)

# =============================================================================
# Auth Fixtures
# =============================================================================


def generate_auth_fixtures(personas: list[str] | None = None) -> list[FixtureSpec]:
    """
    Generate test user fixtures for auth testing.

    Args:
        personas: Optional list of persona names to generate users for

    Returns:
        List of auth-related fixtures
    """
    fixtures: list[FixtureSpec] = [
        FixtureSpec(
            id="auth_test_user",
            entity="User",
            data={
                "email": "test@example.com",
                "password": "testpass123",
                "display_name": "Test User",
            },
            description="Standard test user for auth flows",
        ),
        FixtureSpec(
            id="auth_invalid_credentials",
            entity=None,  # Not a real entity - just test data
            data={
                "email": "test@example.com",
                "password": "wrongpassword",
            },
            description="Invalid credentials for failed login test",
        ),
        FixtureSpec(
            id="auth_new_user",
            entity="User",
            data={
                "email": "newuser@example.com",
                "password": "newpass456",
                "display_name": "New User",
            },
            description="New user for registration test",
        ),
    ]

    # Generate persona-specific fixtures
    if personas:
        for persona in personas:
            fixtures.append(
                FixtureSpec(
                    id=f"auth_user_{persona}",
                    entity="User",
                    data={
                        "email": f"{persona}@example.com",
                        "password": f"{persona}pass123",
                        "display_name": f"{persona.title()} User",
                        "persona": persona,
                    },
                    description=f"Test user with '{persona}' persona",
                )
            )

    return fixtures


# =============================================================================
# Login Flows
# =============================================================================


def generate_login_valid_flow() -> FlowSpec:
    """
    Generate flow for testing valid login.

    Tests that a user can log in with correct credentials.
    """
    steps: list[FlowStep] = [
        FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target="/",  # Root path - works for any app
            description="Navigate to home page",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target="auth:login_button",
            description="Click login button to open modal",
        ),
        FlowStep(
            kind=FlowStepKind.WAIT,
            target="auth:modal",
            value="1000",  # Wait for modal animation
            description="Wait for auth modal to open",
        ),
        FlowStep(
            kind=FlowStepKind.FILL,
            target="auth:field.email",
            fixture_ref="auth_test_user.email",
            description="Enter email address",
        ),
        FlowStep(
            kind=FlowStepKind.FILL,
            target="auth:field.password",
            fixture_ref="auth_test_user.password",
            description="Enter password",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target="auth:submit",
            description="Click submit button",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.LOGIN_SUCCEEDED,
            ),
            description="Assert login succeeded",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.IS_AUTHENTICATED,
            ),
            description="Assert user is authenticated",
        ),
    ]

    return FlowSpec(
        id="auth_login_valid",
        description="Login with valid credentials succeeds",
        priority=FlowPriority.HIGH,
        preconditions=FlowPrecondition(
            authenticated=False,
            fixtures=["auth_test_user"],
        ),
        steps=steps,
        tags=["auth", "login", "happy-path"],
        auto_generated=True,
    )


def generate_login_invalid_flow() -> FlowSpec:
    """
    Generate flow for testing invalid login.

    Tests that login with wrong password shows error.
    """
    steps: list[FlowStep] = [
        FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target="/",  # Root path - works for any app
            description="Navigate to home page",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target="auth:login_button",
            description="Click login button to open modal",
        ),
        FlowStep(
            kind=FlowStepKind.WAIT,
            target="auth:modal",
            value="1000",
            description="Wait for auth modal to open",
        ),
        FlowStep(
            kind=FlowStepKind.FILL,
            target="auth:field.email",
            fixture_ref="auth_invalid_credentials.email",
            description="Enter email address",
        ),
        FlowStep(
            kind=FlowStepKind.FILL,
            target="auth:field.password",
            fixture_ref="auth_invalid_credentials.password",
            description="Enter wrong password",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target="auth:submit",
            description="Click submit button",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.LOGIN_FAILED,
            ),
            description="Assert login failed with error",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.IS_NOT_AUTHENTICATED,
            ),
            description="Assert user is still not authenticated",
        ),
    ]

    return FlowSpec(
        id="auth_login_invalid",
        description="Login with wrong password shows error",
        priority=FlowPriority.HIGH,
        preconditions=FlowPrecondition(
            authenticated=False,
            fixtures=["auth_test_user"],
        ),
        steps=steps,
        tags=["auth", "login", "error-handling"],
        auto_generated=True,
    )


# =============================================================================
# Logout Flow
# =============================================================================


def generate_logout_flow() -> FlowSpec:
    """
    Generate flow for testing logout.

    Tests that logged-in user can log out.
    """
    steps: list[FlowStep] = [
        FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target="/",  # Root path - works for any app
            description="Navigate to home page",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.IS_AUTHENTICATED,
            ),
            description="Assert user is logged in",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target="auth:logout_button",
            description="Click logout button",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.IS_NOT_AUTHENTICATED,
            ),
            description="Assert user is logged out",
        ),
    ]

    return FlowSpec(
        id="auth_logout",
        description="Logout clears session and shows login button",
        priority=FlowPriority.HIGH,
        preconditions=FlowPrecondition(
            authenticated=True,
            fixtures=["auth_test_user"],
        ),
        steps=steps,
        tags=["auth", "logout"],
        auto_generated=True,
    )


# =============================================================================
# Registration Flow
# =============================================================================


def generate_registration_flow() -> FlowSpec:
    """
    Generate flow for testing user registration.

    Tests that a new user can register and is auto-logged in.
    """
    steps: list[FlowStep] = [
        FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target="/",  # Root path - works for any app
            description="Navigate to home page",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target="auth:login_button",
            description="Click login button to open modal",
        ),
        FlowStep(
            kind=FlowStepKind.WAIT,
            target="auth:modal",
            value="1000",
            description="Wait for auth modal to open",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target="auth:toggle.register",
            description="Switch to registration mode",
        ),
        FlowStep(
            kind=FlowStepKind.FILL,
            target="auth:field.email",
            fixture_ref="auth_new_user.email",
            description="Enter email address",
        ),
        FlowStep(
            kind=FlowStepKind.FILL,
            target="auth:field.password",
            fixture_ref="auth_new_user.password",
            description="Enter password",
        ),
        FlowStep(
            kind=FlowStepKind.FILL,
            target="auth:field.display_name",
            fixture_ref="auth_new_user.display_name",
            description="Enter display name",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target="auth:submit",
            description="Click register button",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.LOGIN_SUCCEEDED,
            ),
            description="Assert registration succeeded (auto-login)",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.IS_AUTHENTICATED,
            ),
            description="Assert user is authenticated",
        ),
    ]

    return FlowSpec(
        id="auth_registration",
        description="Register creates account and auto-logs in",
        priority=FlowPriority.HIGH,
        preconditions=FlowPrecondition(
            authenticated=False,
        ),
        steps=steps,
        tags=["auth", "registration", "happy-path"],
        auto_generated=True,
    )


# =============================================================================
# Protected Route Flows
# =============================================================================


def generate_protected_route_flow(
    surface_name: str,
    surface_title: str | None = None,
) -> FlowSpec:
    """
    Generate flow for testing protected route access without auth.

    Args:
        surface_name: Name of the protected surface
        surface_title: Optional human-readable title

    Tests that accessing a protected surface without auth triggers protection.
    """
    title = surface_title or surface_name.replace("_", " ").title()

    steps: list[FlowStep] = [
        FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target=f"view:{surface_name}",
            description=f"Try to access {title} without auth",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.ROUTE_PROTECTED,
            ),
            description="Assert route is protected (modal or redirect)",
        ),
    ]

    return FlowSpec(
        id=f"auth_protected_{surface_name}",
        description=f"Accessing {title} without auth requires login",
        priority=FlowPriority.HIGH,
        preconditions=FlowPrecondition(
            authenticated=False,
        ),
        steps=steps,
        tags=["auth", "protected-route", surface_name],
        auto_generated=True,
    )


def generate_protected_route_with_auth_flow(
    surface_name: str,
    surface_title: str | None = None,
) -> FlowSpec:
    """
    Generate flow for testing protected route access with auth.

    Args:
        surface_name: Name of the protected surface
        surface_title: Optional human-readable title

    Tests that authenticated user can access protected surface.
    """
    title = surface_title or surface_name.replace("_", " ").title()

    steps: list[FlowStep] = [
        FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target=f"view:{surface_name}",
            description=f"Navigate to {title}",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.VISIBLE,
                target=f"view:{surface_name}",
            ),
            description=f"Assert {title} is visible",
        ),
    ]

    return FlowSpec(
        id=f"auth_protected_{surface_name}_allowed",
        description=f"Authenticated user can access {title}",
        priority=FlowPriority.MEDIUM,
        preconditions=FlowPrecondition(
            authenticated=True,
            fixtures=["auth_test_user"],
        ),
        steps=steps,
        tags=["auth", "protected-route", surface_name],
        auto_generated=True,
    )


# =============================================================================
# Persona Access Control Flows
# =============================================================================


def generate_persona_access_allowed_flow(
    persona: str,
    surface_name: str,
    surface_title: str | None = None,
) -> FlowSpec:
    """
    Generate flow for testing allowed persona access.

    Args:
        persona: Persona that should have access
        surface_name: Name of the protected surface
        surface_title: Optional human-readable title
    """
    title = surface_title or surface_name.replace("_", " ").title()

    steps: list[FlowStep] = [
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.HAS_PERSONA,
                target=persona,
            ),
            description=f"Assert user has '{persona}' persona",
        ),
        FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target=f"view:{surface_name}",
            description=f"Navigate to {title}",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.VISIBLE,
                target=f"view:{surface_name}",
            ),
            description=f"Assert {title} is visible",
        ),
    ]

    return FlowSpec(
        id=f"auth_persona_{persona}_{surface_name}_allowed",
        description=f"User with '{persona}' persona can access {title}",
        priority=FlowPriority.MEDIUM,
        preconditions=FlowPrecondition(
            authenticated=True,
            user_role=persona,
            fixtures=[f"auth_user_{persona}"],
        ),
        steps=steps,
        tags=["auth", "rbac", persona, surface_name],
        auto_generated=True,
    )


def generate_persona_access_denied_flow(
    persona: str,
    surface_name: str,
    surface_title: str | None = None,
) -> FlowSpec:
    """
    Generate flow for testing denied persona access.

    Args:
        persona: Persona that should NOT have access
        surface_name: Name of the protected surface
        surface_title: Optional human-readable title
    """
    title = surface_title or surface_name.replace("_", " ").title()

    steps: list[FlowStep] = [
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.HAS_PERSONA,
                target=persona,
            ),
            description=f"Assert user has '{persona}' persona",
        ),
        FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target=f"view:{surface_name}",
            description=f"Try to access {title}",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.ROUTE_PROTECTED,
            ),
            description="Assert access is denied",
        ),
    ]

    return FlowSpec(
        id=f"auth_persona_{persona}_{surface_name}_denied",
        description=f"User with '{persona}' persona cannot access {title}",
        priority=FlowPriority.MEDIUM,
        preconditions=FlowPrecondition(
            authenticated=True,
            user_role=persona,
            fixtures=[f"auth_user_{persona}"],
        ),
        steps=steps,
        tags=["auth", "rbac", persona, surface_name],
        auto_generated=True,
    )


# =============================================================================
# Main Generator
# =============================================================================


def generate_auth_flows_for_surface(
    surface_name: str,
    surface_title: str | None,
    access: SurfaceAccessSpec,
) -> list[FlowSpec]:
    """
    Generate all auth-related flows for a protected surface.

    Args:
        surface_name: Surface identifier
        surface_title: Human-readable title
        access: Surface access specification

    Returns:
        List of auth flows for this surface
    """
    flows: list[FlowSpec] = []

    if not access.require_auth:
        return flows

    # Protected route test (unauthenticated access)
    flows.append(generate_protected_route_flow(surface_name, surface_title))

    # Authenticated access test
    flows.append(generate_protected_route_with_auth_flow(surface_name, surface_title))

    # Persona-specific access tests
    for persona in access.allow_personas:
        flows.append(generate_persona_access_allowed_flow(persona, surface_name, surface_title))

    for persona in access.deny_personas:
        flows.append(generate_persona_access_denied_flow(persona, surface_name, surface_title))

    return flows


def generate_all_auth_flows(
    allow_registration: bool = True,
    protected_surfaces: list[tuple[str, str | None, SurfaceAccessSpec]] | None = None,
) -> tuple[list[FixtureSpec], list[FlowSpec]]:
    """
    Generate all auth-related fixtures and flows.

    Args:
        allow_registration: Whether registration is enabled
        protected_surfaces: List of (name, title, access_spec) tuples

    Returns:
        Tuple of (fixtures, flows)
    """
    # Collect all personas from protected surfaces
    personas: set[str] = set()
    if protected_surfaces:
        for _, _, access in protected_surfaces:
            personas.update(access.allow_personas)
            personas.update(access.deny_personas)

    # Generate fixtures
    fixtures = generate_auth_fixtures(list(personas) if personas else None)

    # Generate core auth flows
    flows: list[FlowSpec] = [
        generate_login_valid_flow(),
        generate_login_invalid_flow(),
        generate_logout_flow(),
    ]

    if allow_registration:
        flows.append(generate_registration_flow())

    # Generate protected surface flows
    if protected_surfaces:
        for surface_name, surface_title, access in protected_surfaces:
            flows.extend(generate_auth_flows_for_surface(surface_name, surface_title, access))

    return fixtures, flows
