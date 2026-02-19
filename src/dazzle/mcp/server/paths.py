"""Centralized path constants — re-exported from ``dazzle.core.paths``.

This shim preserves backward compatibility for the 15+ MCP-layer callers
that import from ``dazzle.mcp.server.paths``.  The canonical definitions
now live in ``dazzle.core.paths`` so that core persistence modules can
use them without a core→mcp dependency.
"""

from dazzle.core.paths import *  # noqa: F401, F403
from dazzle.core.paths import (
    ACTIVITY_LOG_FILE as ACTIVITY_LOG_FILE,
)
from dazzle.core.paths import (
    CAPTURES_DIR as CAPTURES_DIR,
)
from dazzle.core.paths import (
    COMPOSITION_DIR as COMPOSITION_DIR,
)
from dazzle.core.paths import (
    DAZZLE_DIR as DAZZLE_DIR,
)
from dazzle.core.paths import (
    DEMO_DATA_DIR as DEMO_DATA_DIR,
)
from dazzle.core.paths import (
    DISCOVERY_DIR as DISCOVERY_DIR,
)
from dazzle.core.paths import (
    DNR_LOG_FILE as DNR_LOG_FILE,
)
from dazzle.core.paths import (
    KG_DB_FILE as KG_DB_FILE,
)
from dazzle.core.paths import (
    LOGS_DIR as LOGS_DIR,
)
from dazzle.core.paths import (
    MANIFEST_FILE as MANIFEST_FILE,
)
from dazzle.core.paths import (
    OVERRIDES_FILE as OVERRIDES_FILE,
)
from dazzle.core.paths import (
    PROCESSES_DB_FILE as PROCESSES_DB_FILE,
)
from dazzle.core.paths import (
    PROCESSES_DIR as PROCESSES_DIR,
)
from dazzle.core.paths import (
    REFERENCES_DIR as REFERENCES_DIR,
)
from dazzle.core.paths import (
    STORIES_DIR as STORIES_DIR,
)
from dazzle.core.paths import (
    TEST_RESULTS_DIR as TEST_RESULTS_DIR,
)
from dazzle.core.paths import (
    project_activity_log as project_activity_log,
)
from dazzle.core.paths import (
    project_composition_captures as project_composition_captures,
)
from dazzle.core.paths import (
    project_composition_references as project_composition_references,
)
from dazzle.core.paths import (
    project_dazzle_dir as project_dazzle_dir,
)
from dazzle.core.paths import (
    project_demo_data_dir as project_demo_data_dir,
)
from dazzle.core.paths import (
    project_discovery_dir as project_discovery_dir,
)
from dazzle.core.paths import (
    project_kg_db as project_kg_db,
)
from dazzle.core.paths import (
    project_log_dir as project_log_dir,
)
from dazzle.core.paths import (
    project_manifest as project_manifest,
)
from dazzle.core.paths import (
    project_overrides_file as project_overrides_file,
)
from dazzle.core.paths import (
    project_processes_db as project_processes_db,
)
from dazzle.core.paths import (
    project_processes_dir as project_processes_dir,
)
from dazzle.core.paths import (
    project_stories_dir as project_stories_dir,
)
from dazzle.core.paths import (
    project_test_results_dir as project_test_results_dir,
)
