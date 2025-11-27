"""
Action and effect specification types for UISpec.

Defines actions, effects, transitions, and state patches.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from dazzle_dnr_ui.specs.state import Binding


# =============================================================================
# State Patches
# =============================================================================


class PatchOp(str, Enum):
    """Patch operations (JSON Patch style)."""

    SET = "set"
    DELETE = "delete"
    MERGE = "merge"
    APPEND = "append"
    REMOVE = "remove"


class PatchSpec(BaseModel):
    """
    State patch specification.

    Example:
        PatchSpec(op=PatchOp.SET, path="selectedClient", value=client_id)
        PatchSpec(op=PatchOp.APPEND, path="notifications", value=new_notification)
    """

    op: PatchOp = Field(description="Patch operation")
    path: str = Field(description="State path to patch")
    value: Any | None = Field(default=None, description="Value for the patch")

    class Config:
        frozen = True


# =============================================================================
# Transitions
# =============================================================================


class TransitionSpec(BaseModel):
    """
    State transition specification.

    Example:
        TransitionSpec(
            target_state="workspace.selectedClient",
            update=PatchSpec(op=PatchOp.SET, path="selectedClient", value=client)
        )
    """

    target_state: str = Field(description="Target state variable")
    update: PatchSpec = Field(description="Patch to apply")

    class Config:
        frozen = True


# =============================================================================
# Effects
# =============================================================================


class FetchEffect(BaseModel):
    """
    Fetch effect - call backend service.

    Example:
        FetchEffect(
            backend_service="list_clients",
            on_success="handleClientsLoaded",
            on_error="handleError"
        )
    """

    kind: Literal["fetch"] = "fetch"
    backend_service: str = Field(description="Backend service name to call")
    inputs: dict[str, Binding] | None = Field(
        default=None, description="Input bindings for the service"
    )
    on_success: str | None = Field(
        default=None, description="Action to dispatch on success"
    )
    on_error: str | None = Field(
        default=None, description="Action to dispatch on error"
    )

    class Config:
        frozen = True


class NavigateEffect(BaseModel):
    """
    Navigate effect - change route.

    Example:
        NavigateEffect(route="/clients/:id", params={"id": StateBinding(path="selectedClient.id")})
    """

    kind: Literal["navigate"] = "navigate"
    route: str = Field(description="Route path to navigate to")
    params: dict[str, Binding] | None = Field(
        default=None, description="Route parameters"
    )

    class Config:
        frozen = True


class LogEffect(BaseModel):
    """
    Log effect - console.log.

    Example:
        LogEffect(message=LiteralBinding(value="User clicked button"))
    """

    kind: Literal["log"] = "log"
    message: Binding = Field(description="Message to log")
    level: str = Field(default="info", description="Log level (info, warn, error)")

    class Config:
        frozen = True


class ToastEffect(BaseModel):
    """
    Toast effect - show notification.

    Example:
        ToastEffect(
            message=LiteralBinding(value="Client created successfully"),
            variant="success"
        )
    """

    kind: Literal["toast"] = "toast"
    message: Binding = Field(description="Toast message")
    variant: str = Field(
        default="info", description="Toast variant (info, success, warning, error)"
    )
    duration: int | None = Field(
        default=3000, description="Duration in milliseconds"
    )

    class Config:
        frozen = True


class CustomEffect(BaseModel):
    """
    Custom effect - extensibility point.

    Example:
        CustomEffect(name="analytics.track", config={"event": "button_click"})
    """

    kind: Literal["custom"] = "custom"
    name: str = Field(description="Custom effect name")
    config: dict[str, Any] = Field(
        default_factory=dict, description="Effect configuration"
    )

    class Config:
        frozen = True


# Union type for all effects
EffectSpec = FetchEffect | NavigateEffect | LogEffect | ToastEffect | CustomEffect


# =============================================================================
# Actions
# =============================================================================


class ActionSpec(BaseModel):
    """
    Action specification.

    Actions are dispatched in response to user interactions or effects.

    Example:
        ActionSpec(
            name="selectClient",
            inputs=SchemaSpec(fields=[SchemaFieldSpec(name="client_id", type="uuid")]),
            transitions=[
                TransitionSpec(
                    target_state="workspace.selectedClient",
                    update=PatchSpec(op=PatchOp.SET, path="selectedClient", value=client_id)
                )
            ],
            effect=NavigateEffect(route="/clients/:id", params={"id": client_id})
        )
    """

    name: str = Field(description="Action name")
    description: str | None = Field(default=None, description="Action description")
    inputs: dict[str, str] | None = Field(
        default=None, description="Input parameters (name -> type)"
    )
    transitions: list[TransitionSpec] = Field(
        default_factory=list, description="State transitions to apply"
    )
    effect: EffectSpec | None = Field(
        default=None, description="Side effect to execute"
    )

    class Config:
        frozen = True
