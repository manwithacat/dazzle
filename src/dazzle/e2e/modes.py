"""Mode registry for e2e environment orchestration.

Each ModeSpec is a frozen dataclass describing a distinct launch+teardown
profile. The registry is first-class data so MCP consumers can enumerate
available modes without hardcoded strings.

v1 ships mode_a only. Modes B/C/D are specced in
docs/superpowers/specs/2026-04-14-e2e-environment-strategy-design.md but
not wired — adding them is ~40 lines here plus CLI wiring.
"""

from dataclasses import dataclass
from typing import Literal

from dazzle.e2e.errors import UnknownModeError

ModeName = Literal["a", "b", "c", "d"]
DbPolicy = Literal["preserve", "fresh", "restore"]
QaFlagPolicy = Literal["auto_if_personas", "always_on", "always_off"]
LogOutput = Literal["captured_tail_on_fail", "stream_live", "captured_archive"]
Lifetime = Literal["single_run", "long_running"]


@dataclass(frozen=True)
class ModeSpec:
    """Static description of an e2e mode."""

    name: ModeName
    description: str
    db_policy_default: DbPolicy
    # Typed as frozenset[str], not frozenset[DbPolicy]: frozenset of a
    # Literal type has fragile covariance behavior under mypy — tuple
    # literal constructors infer narrowly and the frozenset widens,
    # triggering false-positive type errors at usage sites. Keeping str
    # accepts the minor looseness trade for a cleaner call surface.
    db_policies_allowed: frozenset[str]
    qa_flag_policy: QaFlagPolicy
    log_output: LogOutput
    lifetime: Lifetime
    intended_use: str


MODE_A = ModeSpec(
    name="a",
    description=(
        "Developer one-shot — launch an example app, yield an AppConnection, "
        "tear down when the async with block exits."
    ),
    db_policy_default="preserve",
    db_policies_allowed=frozenset({"preserve", "fresh", "restore"}),
    qa_flag_policy="auto_if_personas",
    log_output="captured_tail_on_fail",
    lifetime="single_run",
    intended_use=(
        "Running /ux-cycle Phase B locally against a specific component, or "
        "invoking the fitness engine interactively from the CLI. Default DB "
        "policy is 'preserve' to respect whatever state you have; pass "
        "--fresh for deterministic seed data, or --db-policy=restore to use "
        "a hash-tagged baseline snapshot."
    ),
)


MODE_REGISTRY: tuple[ModeSpec, ...] = (MODE_A,)


def get_mode(name: str) -> ModeSpec:
    """Return the ModeSpec named `name`.

    Input is normalized (stripped + lowercased) so CLI flags like
    ``--mode=A`` or trailing whitespace don't produce confusing
    UnknownModeError failures. Raises UnknownModeError if no mode matches.
    """
    normalized = name.strip().lower()
    for spec in MODE_REGISTRY:
        if spec.name == normalized:
            return spec
    raise UnknownModeError(
        f"Unknown mode {name!r}. Available modes: {', '.join(m.name for m in MODE_REGISTRY)}"
    )
