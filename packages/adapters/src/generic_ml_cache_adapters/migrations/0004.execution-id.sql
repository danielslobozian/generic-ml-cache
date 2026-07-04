-- Migration 0004: domain-minted execution identity (W1)
-- Add a surrogate execution_id (a domain-minted UUID) as the stable handle the
-- DB-first write path targets, so mark/finalize update the exact row just written
-- WHERE execution_id equals it, never the latest row by key (which a concurrent
-- second writer could have inserted). The column is nullable so pre-existing rows
-- keep a NULL id (they are historical and never re-targeted), while every new row
-- carries a unique UUID. A UNIQUE index treats the multiple legacy NULLs as
-- distinct, so it constrains only the real ids.
ALTER TABLE executions ADD COLUMN execution_id TEXT;
CREATE UNIQUE INDEX idx_executions_execution_id ON executions(execution_id);
