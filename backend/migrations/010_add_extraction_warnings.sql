-- Migration: 010_add_extraction_warnings.sql
-- Purpose: Surface extraction data-loss warnings to the user instead of
--          completing jobs silently with partial data.
-- Date: 2026-06-11

ALTER TABLE boq_jobs
    ADD COLUMN IF NOT EXISTS extraction_warnings JSONB DEFAULT '[]'::jsonb;

COMMENT ON COLUMN boq_jobs.extraction_warnings IS
    'List of extraction warning strings (truncated batches, refused/failed pages).';
