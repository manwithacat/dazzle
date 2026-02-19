"""Centralized path constants for the Dazzle project.

All hardcoded directory and file names that appear across handlers are
collected here so they can be changed in one place.  This module lives in
``dazzle.core`` so that both core persistence layers and the MCP server
can import it without creating a core→mcp dependency.
"""

from __future__ import annotations

from pathlib import Path

# -- Top-level project files -------------------------------------------------
MANIFEST_FILE = "dazzle.toml"

# -- .dazzle runtime directory -----------------------------------------------
DAZZLE_DIR = ".dazzle"

# -- Database files ----------------------------------------------------------
KG_DB_FILE = "knowledge_graph.db"
PROCESSES_DB_FILE = "processes.db"

# -- Subdirectory names under .dazzle ----------------------------------------
DISCOVERY_DIR = "discovery"
COMPOSITION_DIR = "composition"
CAPTURES_DIR = "captures"
REFERENCES_DIR = "references"
LOGS_DIR = "logs"
TEST_RESULTS_DIR = "test_results"
STORIES_DIR = "stories"
DEMO_DATA_DIR = "demo_data"
PROCESSES_DIR = "processes"

# -- Override registry -------------------------------------------------------
OVERRIDES_FILE = "overrides.json"

# -- Log files ---------------------------------------------------------------
ACTIVITY_LOG_FILE = "mcp-activity.log"
DNR_LOG_FILE = "dazzle.log"


# -- Helper functions --------------------------------------------------------


def project_dazzle_dir(project_root: Path) -> Path:
    """Return the .dazzle directory for a project."""
    return project_root / DAZZLE_DIR


def project_manifest(project_root: Path) -> Path:
    """Return the path to dazzle.toml for a project."""
    return project_root / MANIFEST_FILE


def project_kg_db(project_root: Path) -> Path:
    """Return the knowledge graph database path for a project."""
    return project_dazzle_dir(project_root) / KG_DB_FILE


def project_processes_db(project_root: Path) -> Path:
    """Return the processes database path for a project."""
    return project_dazzle_dir(project_root) / PROCESSES_DB_FILE


def project_discovery_dir(project_root: Path) -> Path:
    """Return the discovery reports directory for a project."""
    return project_dazzle_dir(project_root) / DISCOVERY_DIR


def project_composition_captures(project_root: Path) -> Path:
    """Return the composition captures directory for a project."""
    return project_dazzle_dir(project_root) / COMPOSITION_DIR / CAPTURES_DIR


def project_composition_references(project_root: Path) -> Path:
    """Return the composition references directory for a project."""
    return project_dazzle_dir(project_root) / COMPOSITION_DIR / REFERENCES_DIR


def project_log_dir(project_root: Path) -> Path:
    """Return the logs directory for a project."""
    return project_dazzle_dir(project_root) / LOGS_DIR


def project_activity_log(project_root: Path) -> Path:
    """Return the activity log path for a project."""
    return project_dazzle_dir(project_root) / ACTIVITY_LOG_FILE


def project_test_results_dir(project_root: Path) -> Path:
    """Return the test results directory for a project."""
    return project_dazzle_dir(project_root) / TEST_RESULTS_DIR


def project_stories_dir(project_root: Path) -> Path:
    """Return the stories directory for a project."""
    return project_dazzle_dir(project_root) / STORIES_DIR


def project_demo_data_dir(project_root: Path) -> Path:
    """Return the demo data directory for a project."""
    return project_dazzle_dir(project_root) / DEMO_DATA_DIR


def project_processes_dir(project_root: Path) -> Path:
    """Return the processes directory for a project."""
    return project_dazzle_dir(project_root) / PROCESSES_DIR


def project_overrides_file(project_root: Path) -> Path:
    """Return the overrides registry path for a project."""
    return project_dazzle_dir(project_root) / OVERRIDES_FILE
