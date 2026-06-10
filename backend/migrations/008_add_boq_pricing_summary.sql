-- Migration: 008_add_boq_pricing_summary.sql
-- Purpose: Support BoQ market pricing pipeline (boq_pricer.py)
-- Date: 2026-06-10

-- ============================================
-- 1. BoQ job pricing summary fields
-- ============================================
-- _calculate_summary_sync writes these after pricing completes

ALTER TABLE boq_jobs
    ADD COLUMN IF NOT EXISTS savings_percent DECIMAL(5, 2),
    ADD COLUMN IF NOT EXISTS priced_count INT DEFAULT 0;

COMMENT ON COLUMN boq_jobs.savings_percent IS 'potential_savings / contractor_total * 100';
COMMENT ON COLUMN boq_jobs.priced_count IS 'Number of items with a successful marketplace price match';

-- ============================================
-- 2. Unique index on materials.normalized_name
-- ============================================
-- boq_pricer._write_cache upserts with on_conflict=normalized_name, which
-- requires a unique index. The partial index from migration 006 is neither
-- unique nor inferable as an ON CONFLICT arbiter (PostgREST omits the
-- predicate), so replace it with a full unique index. Multiple NULLs remain
-- allowed for legacy rows that predate normalization.

DROP INDEX IF EXISTS idx_materials_normalized_name;

CREATE UNIQUE INDEX IF NOT EXISTS idx_materials_normalized_name_unique
ON materials (normalized_name);
