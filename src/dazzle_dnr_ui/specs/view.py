"""
View specification types for UISpec.

Defines view trees for component rendering.
"""

from typing import Literal

from pydantic import BaseModel, Field

from dazzle_dnr_ui.specs.state import Binding

# =============================================================================
# View Nodes
# =============================================================================


class ElementNode(BaseModel):
    """
    DOM element node.

    Example:
        ElementNode(
            as="Card",
            props={"title": LiteralBinding(value="Client Details")},
            children=[...]
        )
    """

    kind: Literal["element"] = "element"
    as_: str = Field(description="Component or element name", alias="as")  # 'as' is Python keyword
    props: dict[str, Binding] = Field(
        default_factory=dict, description="Element props with bindings"
    )
    children: list["ViewNode"] = Field(default_factory=list, description="Child nodes")

    class Config:
        frozen = True
        populate_by_name = True  # Allow both 'as' and 'as_'


class ConditionalNode(BaseModel):
    """
    Conditional rendering node.

    Example:
        ConditionalNode(
            condition=DerivedBinding(expr="isLoading"),
            then_branch=ElementNode(as="Spinner"),
            else_branch=ElementNode(as="Content")
        )
    """

    kind: Literal["conditional"] = "conditional"
    condition: Binding = Field(description="Condition binding")
    then_branch: "ViewNode" = Field(description="Node to render if true")
    else_branch: "ViewNode | None" = Field(default=None, description="Node to render if false")

    class Config:
        frozen = True


class LoopNode(BaseModel):
    """
    Loop/iteration node.

    Example:
        LoopNode(
            items=StateBinding(path="clients"),
            item_var="client",
            key_path="id",
            template=ElementNode(as="ClientCard", props={"client": PropBinding(path="client")})
        )
    """

    kind: Literal["loop"] = "loop"
    items: Binding = Field(description="Array binding to iterate over")
    item_var: str = Field(description="Variable name for each item")
    key_path: str = Field(description="Path to unique key in item (for efficient re-rendering)")
    template: "ViewNode" = Field(description="Template to render for each item")

    class Config:
        frozen = True


class SlotNode(BaseModel):
    """
    Content slot for component composition.

    Example:
        SlotNode(name="header", fallback=ElementNode(as="DefaultHeader"))
    """

    kind: Literal["slot"] = "slot"
    name: str = Field(description="Slot name")
    fallback: "ViewNode | None" = Field(
        default=None, description="Fallback content if slot not filled"
    )

    class Config:
        frozen = True


class TextNode(BaseModel):
    """
    Text content node.

    Example:
        TextNode(content=LiteralBinding(value="Hello World"))
        TextNode(content=PropBinding(path="client.name"))
    """

    kind: Literal["text"] = "text"
    content: Binding = Field(description="Text content binding")

    class Config:
        frozen = True


# Union type for all view nodes
ViewNode = ElementNode | ConditionalNode | LoopNode | SlotNode | TextNode


# Update forward references
ElementNode.model_rebuild()
ConditionalNode.model_rebuild()
LoopNode.model_rebuild()
SlotNode.model_rebuild()
