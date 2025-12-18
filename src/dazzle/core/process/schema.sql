-- SQLite schema for LiteProcessAdapter process persistence
-- This schema supports workflow state, human tasks, and schedules

-- Process run instances
CREATE TABLE IF NOT EXISTS process_runs (
    run_id TEXT PRIMARY KEY,
    process_name TEXT NOT NULL,
    process_version TEXT NOT NULL DEFAULT 'v1',
    dsl_version TEXT NOT NULL DEFAULT '0.1',
    status TEXT NOT NULL DEFAULT 'pending',
    current_step TEXT,
    inputs JSON NOT NULL DEFAULT '{}',
    context JSON NOT NULL DEFAULT '{}',
    outputs JSON,
    error TEXT,
    idempotency_key TEXT UNIQUE,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Human tasks within process runs
CREATE TABLE IF NOT EXISTS process_tasks (
    task_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES process_runs(run_id) ON DELETE CASCADE,
    step_name TEXT NOT NULL,
    surface_name TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    assignee_id TEXT,
    assignee_role TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    outcome TEXT,
    outcome_data JSON,
    due_at TIMESTAMP NOT NULL,
    escalated_at TIMESTAMP,
    completed_at TIMESTAMP,
    completed_by TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Schedule tracking for cron/interval jobs
CREATE TABLE IF NOT EXISTS schedule_runs (
    schedule_name TEXT PRIMARY KEY,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    last_run_id TEXT,
    run_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Step execution history for audit and debugging
CREATE TABLE IF NOT EXISTS step_executions (
    execution_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES process_runs(run_id) ON DELETE CASCADE,
    step_name TEXT NOT NULL,
    step_kind TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    inputs JSON,
    outputs JSON,
    error TEXT,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms INTEGER
);

-- Signals sent to processes
CREATE TABLE IF NOT EXISTS process_signals (
    signal_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES process_runs(run_id) ON DELETE CASCADE,
    signal_name TEXT NOT NULL,
    payload JSON,
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);

-- Process event log for HLESS event emission
CREATE TABLE IF NOT EXISTS process_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    process_name TEXT NOT NULL,
    schema_name TEXT NOT NULL,
    event_data JSON NOT NULL,
    published BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_runs_status ON process_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_process ON process_runs(process_name);
CREATE INDEX IF NOT EXISTS idx_runs_idempotency ON process_runs(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_runs_updated ON process_runs(updated_at);

CREATE INDEX IF NOT EXISTS idx_tasks_run ON process_tasks(run_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON process_tasks(assignee_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON process_tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON process_tasks(due_at) WHERE status IN ('pending', 'assigned');

CREATE INDEX IF NOT EXISTS idx_steps_run ON step_executions(run_id);
CREATE INDEX IF NOT EXISTS idx_steps_name ON step_executions(run_id, step_name);

CREATE INDEX IF NOT EXISTS idx_signals_run ON process_signals(run_id, processed);
CREATE INDEX IF NOT EXISTS idx_events_published ON process_events(published, created_at);

-- Trigger to update updated_at on process_runs
CREATE TRIGGER IF NOT EXISTS update_process_runs_timestamp
    AFTER UPDATE ON process_runs
    FOR EACH ROW
    WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE process_runs SET updated_at = CURRENT_TIMESTAMP WHERE run_id = NEW.run_id;
END;

-- Trigger to update updated_at on schedule_runs
CREATE TRIGGER IF NOT EXISTS update_schedule_runs_timestamp
    AFTER UPDATE ON schedule_runs
    FOR EACH ROW
    WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE schedule_runs SET updated_at = CURRENT_TIMESTAMP WHERE schedule_name = NEW.schedule_name;
END;

-- ============================================================
-- Version Management Tables (Phase 6: Migration and Versioning)
-- ============================================================

-- Track DSL versions for process versioning
CREATE TABLE IF NOT EXISTS dsl_versions (
    version_id TEXT PRIMARY KEY,
    deployed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dsl_hash TEXT NOT NULL,
    manifest_json JSON NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'  -- active, draining, archived
);

-- Track version transitions during migrations
CREATE TABLE IF NOT EXISTS version_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_version TEXT REFERENCES dsl_versions(version_id),
    to_version TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'in_progress',  -- in_progress, completed, failed, rolled_back
    runs_drained INTEGER DEFAULT 0,
    runs_remaining INTEGER DEFAULT 0
);

-- Indexes for version management queries
CREATE INDEX IF NOT EXISTS idx_versions_status ON dsl_versions(status);
CREATE INDEX IF NOT EXISTS idx_versions_deployed ON dsl_versions(deployed_at DESC);
CREATE INDEX IF NOT EXISTS idx_migrations_status ON version_migrations(status);
CREATE INDEX IF NOT EXISTS idx_runs_dsl_version ON process_runs(dsl_version) WHERE dsl_version IS NOT NULL;
