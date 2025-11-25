"""
Vocabulary system for DAZZLE - App-local vocabulary and extension packs.

Enables apps to define reusable patterns (macros/aliases) that expand to core DSL.
This module provides the schema and utilities for managing vocabulary entries.
"""

from datetime import datetime
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

    def get_param(self, name: str) -> VocabParameter | None:
        """Get parameter definition by name."""
        for param in self.parameters:
            if param.name == name:
                return param
        return None

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

    def increment_usage(self) -> "VocabEntry":
        """
        Increment usage count.

        Returns a new VocabEntry with updated metadata (entries are immutable).
        """
        new_metadata = self.metadata.copy()
        new_metadata["usage_count"] = self.usage_count + 1
        new_metadata["last_used_at"] = datetime.utcnow().isoformat()

        return VocabEntry(
            id=self.id,
            kind=self.kind,
            scope=self.scope,
            dsl_core_version=self.dsl_core_version,
            description=self.description,
            parameters=self.parameters,
            expansion=self.expansion,
            metadata=new_metadata,
            tags=self.tags,
        )

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

    def add_entry(self, entry: VocabEntry) -> "VocabManifest":
        """
        Add a new vocabulary entry.

        Returns a new VocabManifest with the entry added (manifests are immutable).

        Raises:
            ValueError: If entry ID already exists
        """
        if self.get_entry(entry.id):
            raise ValueError(f"Entry '{entry.id}' already exists in manifest")

        return VocabManifest(
            version=self.version,
            app_id=self.app_id,
            dsl_core_version=self.dsl_core_version,
            entries=self.entries + [entry],
        )

    def get_entry(self, entry_id: str) -> VocabEntry | None:
        """Get entry by ID."""
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        return None

    def update_entry(self, entry: VocabEntry) -> "VocabManifest":
        """
        Update an existing entry.

        Returns a new VocabManifest with the entry updated.

        Raises:
            ValueError: If entry doesn't exist
        """
        if not self.get_entry(entry.id):
            raise ValueError(f"Entry '{entry.id}' not found in manifest")

        new_entries = [e if e.id != entry.id else entry for e in self.entries]

        return VocabManifest(
            version=self.version,
            app_id=self.app_id,
            dsl_core_version=self.dsl_core_version,
            entries=new_entries,
        )

    def remove_entry(self, entry_id: str) -> "VocabManifest":
        """
        Remove an entry.

        Returns a new VocabManifest with the entry removed.

        Raises:
            ValueError: If entry doesn't exist
        """
        if not self.get_entry(entry_id):
            raise ValueError(f"Entry '{entry_id}' not found in manifest")

        new_entries = [e for e in self.entries if e.id != entry_id]

        return VocabManifest(
            version=self.version,
            app_id=self.app_id,
            dsl_core_version=self.dsl_core_version,
            entries=new_entries,
        )

    def filter_by_scope(self, scope: str) -> list[VocabEntry]:
        """Get all entries with given scope."""
        return [e for e in self.entries if e.scope == scope]

    def filter_by_kind(self, kind: str) -> list[VocabEntry]:
        """Get all entries with given kind."""
        return [e for e in self.entries if e.kind == kind]

    def filter_by_tag(self, tag: str) -> list[VocabEntry]:
        """Get all entries with given tag."""
        return [e for e in self.entries if tag in e.tags]

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

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError(f"Empty or invalid YAML in {path}")

    return VocabManifest(**data)


def save_manifest(manifest: VocabManifest, path: Path) -> None:
    """
    Save vocabulary manifest to YAML file.

    Args:
        manifest: VocabManifest to save
        path: Path to manifest.yml
    """
    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict
    data = manifest.model_dump(mode="json")

    # Write YAML
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def create_empty_manifest(app_id: str, dsl_core_version: str = "1.0.0") -> VocabManifest:
    """
    Create an empty vocabulary manifest.

    Args:
        app_id: Unique app identifier
        dsl_core_version: Target core DSL version

    Returns:
        Empty VocabManifest
    """
    return VocabManifest(
        version="1.0.0", app_id=app_id, dsl_core_version=dsl_core_version, entries=[]
    )
