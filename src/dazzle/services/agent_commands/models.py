"""Data models for agent command definitions."""

from dataclasses import dataclass, field


@dataclass
class MaturityGate:
    """Prerequisites that must be met before a command can run."""

    min_entities: int = 0
    min_surfaces: int = 0
    min_stories: int = 0
    requires_running_app: bool = False
    requires_github_remote: bool = False
    requires_spec_md: bool = False
    requires: list[str] = field(default_factory=list)


@dataclass
class LoopConfig:
    """Configuration for loop-pattern commands."""

    backlog_file: str = ""
    log_file: str = ""
    lock_file: str = ""
    max_cycles: int = 50
    stale_lock_minutes: int = 30


@dataclass
class ToolsConfig:
    """MCP and CLI tools available to the command."""

    mcp: list[str] = field(default_factory=list)
    cli: list[str] = field(default_factory=list)


@dataclass
class CommandDefinition:
    """A fully resolved agent command definition loaded from TOML."""

    name: str
    version: str
    title: str
    description: str
    pattern: str  # "loop" | "one-shot"
    maturity: MaturityGate = field(default_factory=MaturityGate)
    loop: LoopConfig | None = None
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    template_file: str = ""


@dataclass
class CommandStatus:
    """Availability status of a single command in the sync manifest."""

    version: str
    available: bool
    reason: str | None = None


@dataclass
class SyncManifest:
    """Manifest tracking which commands are synced and available."""

    dazzle_version: str
    commands_version: str
    synced_at: str
    commands: dict[str, CommandStatus] = field(default_factory=dict)
