-- Migration 0002: database integrity constraints
-- Adds the foreign keys 0001 lacked (integrity had rested on repository discipline)
-- and the session-tag uniqueness that execution_tags already had. SQLite cannot
-- ALTER-add a FK or UNIQUE, so each affected table is rebuilt: create-with-constraints
-- -> copy -> drop -> rename. Pre-existing orphan child rows (whose execution_id no
-- longer names a row in executions) are purged during the copy, so a released 0.x DB
-- with real data lands consistent. The runner rebuilds with foreign_keys OFF (its own
-- connection) while normal connections run with foreign_keys ON (the datasource factory).

-- artifacts: FK to executions(id), ON DELETE CASCADE
CREATE TABLE artifacts_new (
    id            INTEGER PRIMARY KEY,
    execution_id  INTEGER NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    name          TEXT,
    encoding      TEXT NOT NULL,
    blob_key      TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL
);
INSERT INTO artifacts_new (id, execution_id, artifact_type, name, encoding, blob_key, size_bytes)
    SELECT id, execution_id, artifact_type, name, encoding, blob_key, size_bytes
    FROM artifacts WHERE execution_id IN (SELECT id FROM executions);
DROP TABLE artifacts;
ALTER TABLE artifacts_new RENAME TO artifacts;
CREATE INDEX idx_artifacts_execution ON artifacts(execution_id);

-- token_usage: FK to executions(id), ON DELETE CASCADE
CREATE TABLE token_usage_new (
    execution_id       INTEGER PRIMARY KEY REFERENCES executions(id) ON DELETE CASCADE,
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    cache_read_tokens  INTEGER,
    cache_write_tokens INTEGER,
    reasoning_tokens   INTEGER,
    cost_usd           REAL,
    raw_json           TEXT NOT NULL
);
INSERT INTO token_usage_new (execution_id, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, reasoning_tokens, cost_usd, raw_json)
    SELECT execution_id, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, reasoning_tokens, cost_usd, raw_json
    FROM token_usage WHERE execution_id IN (SELECT id FROM executions);
DROP TABLE token_usage;
ALTER TABLE token_usage_new RENAME TO token_usage;

-- execution_tags: FK to executions(id), ON DELETE CASCADE (keeps its UNIQUE)
CREATE TABLE execution_tags_new (
    execution_id INTEGER NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    tag          TEXT NOT NULL,
    UNIQUE(execution_id, tag)
);
INSERT INTO execution_tags_new (execution_id, tag)
    SELECT DISTINCT execution_id, tag
    FROM execution_tags WHERE execution_id IN (SELECT id FROM executions);
DROP TABLE execution_tags;
ALTER TABLE execution_tags_new RENAME TO execution_tags;

-- session_tags: gain UNIQUE(session_id, tag) matching execution_tags, dedup existing rows
CREATE TABLE session_tags_new (
    id         INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    tag        TEXT NOT NULL,
    UNIQUE(session_id, tag)
);
INSERT INTO session_tags_new (session_id, tag)
    SELECT session_id, tag FROM session_tags GROUP BY session_id, tag;
DROP TABLE session_tags;
ALTER TABLE session_tags_new RENAME TO session_tags;
