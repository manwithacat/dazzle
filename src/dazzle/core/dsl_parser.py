"""
DSL Parser for DAZZLE.

This module re-exports the modular parser from the parser package.
The parser has been split into smaller, focused modules for better
maintainability and LLM context handling.

For implementation details, see the parser/ package:
- parser/base.py - Base parser class with token utilities
- parser/types.py - Field type parsing
- parser/conditions.py - Condition expression parsing
- parser/entity.py - Entity and archetype parsing
- parser/surface.py - Surface parsing
- parser/service.py - Service and foreign model parsing
- parser/integration.py - Integration parsing
- parser/test.py - Test parsing
- parser/flow.py - E2E flow parsing
- parser/ux.py - UX semantic layer parsing
- parser/workspace.py - Workspace parsing
"""

# Re-export everything from the dsl_parser_impl package for backwards compatibility
from .dsl_parser_impl import (
    Parser,
    parse_dsl,
    BaseParser,
    TypeParserMixin,
    ConditionParserMixin,
    EntityParserMixin,
    SurfaceParserMixin,
    ServiceParserMixin,
    IntegrationParserMixin,
    TestParserMixin,
    FlowParserMixin,
    UXParserMixin,
    WorkspaceParserMixin,
)

__all__ = [
    "Parser",
    "parse_dsl",
    "BaseParser",
    "TypeParserMixin",
    "ConditionParserMixin",
    "EntityParserMixin",
    "SurfaceParserMixin",
    "ServiceParserMixin",
    "IntegrationParserMixin",
    "TestParserMixin",
    "FlowParserMixin",
    "UXParserMixin",
    "WorkspaceParserMixin",
]
