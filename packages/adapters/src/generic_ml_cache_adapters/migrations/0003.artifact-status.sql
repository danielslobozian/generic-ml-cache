-- Migration 0003: per-artifact persistence status (C-4)
-- Give each artifact a blob-persistence lifecycle so DB-first ordering is safe.
-- The row is written PENDING before the blob is put, flipped to STORED once the
-- blob lands, or FAILED (with a detail message) when the write fails. Readers trust
-- only STORED, and an execution is servable (output_persisted=1) only when all of
-- its artifacts are STORED. Plain ADD COLUMN (no FK/unique change, no table rebuild).
-- Existing rows predate the feature and their blobs already exist, so they default
-- to 'stored' with a NULL persisted_at (unknown, pre-status).
ALTER TABLE artifacts ADD COLUMN status TEXT NOT NULL DEFAULT 'stored';
ALTER TABLE artifacts ADD COLUMN persisted_at TEXT;
ALTER TABLE artifacts ADD COLUMN status_detail TEXT;
