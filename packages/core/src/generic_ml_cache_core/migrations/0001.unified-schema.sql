-- Migration 0001: unified schema
-- Merges executions.sqlite3 + registry.sqlite3 into a single database.
-- No IF NOT EXISTS: yoyo guarantees each migration runs exactly once.

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
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_key     TEXT NOT NULL,
    kind              TEXT NOT NULL,
    state             TEXT NOT NULL,
    output_persisted  INTEGER NOT NULL,
    superseded_at     TEXT,
    failure_reason    TEXT,
    failure_message   TEXT,
    failure_exit_code INTEGER,
    created_at        TEXT NOT NULL
);
CREATE INDEX idx_executions_key ON executions(execution_key);

CREATE TABLE artifacts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id  INTEGER NOT NULL,
    artifact_type TEXT NOT NULL,
    name          TEXT,
    encoding      TEXT NOT NULL,
    blob_key      TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL
);
CREATE INDEX idx_artifacts_execution ON artifacts(execution_id);

CREATE TABLE token_usage (
    execution_id       INTEGER PRIMARY KEY,
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    cache_read_tokens  INTEGER,
    cache_write_tokens INTEGER,
    reasoning_tokens   INTEGER,
    cost_usd           REAL,
    raw_json           TEXT NOT NULL
);

CREATE TABLE execution_tags (
    execution_id INTEGER NOT NULL,
    tag          TEXT NOT NULL,
    UNIQUE(execution_id, tag)
);

-- ── access registry subsystem ─────────────────────────────────────────────────

CREATE TABLE access_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    event      TEXT NOT NULL,
    match_key  TEXT,
    client     TEXT,
    model      TEXT,
    effort     TEXT,
    session_id TEXT
);

CREATE TABLE session_tags (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tag        TEXT NOT NULL
);

CREATE TABLE session_specs (
    session_id TEXT PRIMARY KEY,
    client     TEXT NOT NULL,
    model      TEXT NOT NULL,
    effort     TEXT NOT NULL
);
