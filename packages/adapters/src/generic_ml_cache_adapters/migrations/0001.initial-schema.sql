-- Migration 0001: initial schema
-- The single initial schema for a fresh store. Pre-1.0, every schema change is a
-- full store reset (one user, resets freely), so the incremental in-place history
-- earned none of its value while carrying its bugs — this file compresses that
-- history (former 0001 unified-schema + 0002 integrity-constraints + 0003
-- artifact-status + 0004 execution-id) into one create-from-final-state file. The
-- former 0005 was a pre-release DATA reset (DELETE FROM artifacts) a fresh store
-- does not need. Real per-version migrations resume at 1.0.0, where the backwards-
-- compatibility promise makes them worth their cost. A migration file must NOT
-- contain its own transaction control — the runner owns BEGIN/COMMIT.

-- ── executions subsystem ─────────────────────────────────────────────────────

CREATE TABLE call_identities (
    execution_key TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    client        TEXT NOT NULL,
    model         TEXT NOT NULL,
    effort        TEXT NOT NULL,
    identity_json TEXT NOT NULL
);

CREATE TABLE executions (
    id                INTEGER PRIMARY KEY,
    execution_key     TEXT NOT NULL,
    kind              TEXT NOT NULL,
    state             TEXT NOT NULL,
    output_persisted  INTEGER NOT NULL,
    superseded_at     TEXT,
    failure_reason    TEXT,
    failure_message   TEXT,
    failure_exit_code INTEGER,
    created_at        TEXT NOT NULL,
    execution_id      TEXT
);
CREATE INDEX idx_executions_key ON executions(execution_key);
-- The multiple legacy NULL execution_ids count as distinct, so this constrains only
-- real domain-minted UUIDs (W1: the stable handle the DB-first write path targets).
CREATE UNIQUE INDEX idx_executions_execution_id ON executions(execution_id);

CREATE TABLE artifacts (
    id            INTEGER PRIMARY KEY,
    execution_id  INTEGER NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    name          TEXT,
    encoding      TEXT NOT NULL,
    blob_key      TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL,
    status        TEXT NOT NULL DEFAULT 'stored',
    persisted_at  TEXT,
    status_detail TEXT
);
CREATE INDEX idx_artifacts_execution ON artifacts(execution_id);

CREATE TABLE token_usage (
    execution_id       INTEGER PRIMARY KEY REFERENCES executions(id) ON DELETE CASCADE,
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    cache_read_tokens  INTEGER,
    cache_write_tokens INTEGER,
    reasoning_tokens   INTEGER,
    cost_usd           REAL,
    raw_json           TEXT NOT NULL
);

CREATE TABLE execution_tags (
    execution_id INTEGER NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    tag          TEXT NOT NULL,
    UNIQUE(execution_id, tag)
);

-- ── access registry subsystem ─────────────────────────────────────────────────

CREATE TABLE access_events (
    id         INTEGER PRIMARY KEY,
    ts         TEXT NOT NULL,
    event      TEXT NOT NULL,
    match_key  TEXT,
    client     TEXT,
    model      TEXT,
    effort     TEXT,
    session_id TEXT
);

CREATE TABLE session_tags (
    id         INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    tag        TEXT NOT NULL,
    UNIQUE(session_id, tag)
);

CREATE TABLE session_specs (
    session_id TEXT PRIMARY KEY,
    client     TEXT NOT NULL,
    model      TEXT NOT NULL,
    effort     TEXT NOT NULL
);
