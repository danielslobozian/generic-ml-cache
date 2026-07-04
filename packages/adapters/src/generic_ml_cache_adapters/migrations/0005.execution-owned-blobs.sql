-- Migration 0005: execution-owned blobs (X25)
-- The blob key format changes from a bare content fingerprint (a blob shared by
-- every execution with identical bytes) to <execution_id>_<content fingerprint>
-- (each blob owned by exactly one execution). A pre-existing store holds rows whose
-- blob_key is the old shared format, and the new deletion path removes "an
-- execution's own blobs" unconditionally -- which would destroy a blob another row
-- still shares under the old scheme. So the artifact index is cleared and every
-- entry is marked non-servable (output_persisted = 0): each prior entry re-runs as a
-- clean miss and is re-stored under the new owned-blob keys. The old blob FILES on
-- disk are outside the database and are not touched here; a store reset removes them
-- (pre-1.0, users reset -- there is no in-place blob re-keying).
DELETE FROM artifacts;
UPDATE executions SET output_persisted = 0;
