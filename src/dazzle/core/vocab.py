"""
Vocabulary system for DAZZLE - App-local vocabulary and extension packs.

Enables apps to define reusable patterns (macros/aliases) that expand to core DSL.
This module provides the schema and utilities for managing vocabulary entries.
"""

from __future__ import annotations  # required: forward reference

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class VocabParameter(BaseModel):
    """
    Parameter definition for a vocabulary entry.

    Defines inputs that can be substituted into the vocabulary expansion.
    """

    name: str = Field(..., pattern=r"^[a-z_][a-z0-9_]*$", description="Parameter name (snake_case)")
    type: str = Field(..., description="Parameter type (model_ref, string, boolean, number, list)")
    required: bool = Field(default=True, description="Whether parameter is required")
    default: Any | None = Field(default=None, description="Default value if not required")
    description: str | None = Field(
        default=None, description="Human-readable parameter description"
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate parameter type."""
        valid_types = {"model_ref", "string", "boolean", "number", "list", "dict"}
        if v not in valid_types:
            raise ValueError(
                f"Invalid parameter type '{v}'. Must be one of: {', '.join(valid_types)}"
            )
        return v

    model_config = {"frozen": True}


class VocabEntry(BaseModel):
    """
    A single vocabulary entry (macro/alias/pattern).

    Represents a reusable pattern that expands to core DSL.
    """

    id: str = Field(..., pattern=r"^[a-z0-9_]+$", description="Unique identifier (snake_case)")
    kind: str = Field(..., description="Entry kind")
    scope: str = Field(..., description="Entry scope/category")
    dsl_core_version: str = Field(..., description="Target core DSL version")
    description: str = Field(..., description="Human-readable description")
    parameters: list[VocabParameter] = Field(
        default_factory=list, description="Parameter definitions"
    )
    expansion: dict[str, str] = Field(..., description="Expansion to core DSL")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        """Validate entry kind."""
        valid_kinds = {"macro", "alias", "pattern"}
        if v not in valid_kinds:
            raise ValueError(f"Invalid kind '{v}'. Must be one of: {', '.join(valid_kinds)}")
        return v

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        """Validate entry scope."""
        valid_scopes = {"ui", "data", "workflow", "auth", "misc"}
        if v not in valid_scopes:
            raise ValueError(f"Invalid scope '{v}'. Must be one of: {', '.join(valid_scopes)}")
        return v

    @field_validator("expansion")
    @classmethod
    def validate_expansion(cls, v: dict[str, str]) -> dict[str, str]:
        """Validate expansion structure."""
        if "language" not in v:
            raise ValueError("Expansion must include 'language' key")
        if "body" not in v:
            raise ValueError("Expansion must include 'body' key")
        if v["language"] != "dazzle-core-dsl":
            raise ValueError("Expansion language must be 'dazzle-core-dsl'")
        return v

    @property
    def stability(self) -> str:
        """Get stability level from metadata."""
        result = self.metadata.get("stability", "experimental")
        return str(result) if result else "experimental"

    @property
    def usage_count(self) -> int:
        """Get usage count from metadata."""
        result = self.metadata.get("usage_count", 0)
        return int(result) if isinstance(result, int | float | str) else 0

    model_config = {"frozen": True}


class VocabManifest(BaseModel):
    """
    Vocabulary manifest for an app.

    Contains all vocabulary entries defined in an app.
    """

    version: str = Field(default="1.0.0", description="Manifest version (semver)")
    app_id: str = Field(..., description="Unique app identifier")
    dsl_core_version: str = Field(..., description="Target core DSL version")
    entries: list[VocabEntry] = Field(default_factory=list, description="Vocabulary entries")

    def get_entry(self, entry_id: str) -> VocabEntry | None:
        """Get entry by ID."""
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        return None

    model_config = {"frozen": True}


# Serialization helpers


def load_manifest(path: Path) -> VocabManifest:
    """
    Load vocabulary manifest from YAML file.

    Args:
        path: Path to manifest.yml

    Returns:
        VocabManifest instance

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If YAML is invalid or doesn't match schema
    """
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError(f"Empty or invalid YAML in {path}")

    return VocabManifest(**data)
