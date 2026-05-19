CREATE TABLE IF NOT EXISTS runs (
  run_id          TEXT PRIMARY KEY,
  started_at      TEXT NOT NULL,
  ended_at        TEXT,
  app_name        TEXT,
  manifest_path   TEXT,
  command_line    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spans (
  span_id         TEXT PRIMARY KEY,
  trace_id        TEXT NOT NULL,
  parent_span_id  TEXT,
  run_id          TEXT NOT NULL,
  name            TEXT NOT NULL,
  kind            TEXT NOT NULL,
  status          TEXT NOT NULL,
  started_ns      INTEGER NOT NULL,
  ended_ns        INTEGER NOT NULL,
  duration_ns     INTEGER NOT NULL,
  attributes_json TEXT NOT NULL,
  FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_spans_run_id          ON spans(run_id);
CREATE INDEX IF NOT EXISTS idx_spans_parent          ON spans(run_id, parent_span_id);
CREATE INDEX IF NOT EXISTS idx_spans_name_duration   ON spans(run_id, name, duration_ns DESC);

CREATE TABLE IF NOT EXISTS events (
  event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  span_id         TEXT NOT NULL,
  run_id          TEXT NOT NULL,
  name            TEXT NOT NULL,
  timestamp_ns    INTEGER NOT NULL,
  attributes_json TEXT NOT NULL,
  FOREIGN KEY (span_id) REFERENCES spans(span_id)
);

CREATE INDEX IF NOT EXISTS idx_events_span ON events(span_id);
