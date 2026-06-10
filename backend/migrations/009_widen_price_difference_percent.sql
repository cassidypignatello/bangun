-- Migration: 009_widen_price_difference_percent.sql
-- Purpose: Prevent numeric overflow when a marketplace match is far off the
--          contractor price (observed: -4014% on a bad product match, which
--          crashed persist_price_results and failed the whole job).
-- Date: 2026-06-10

ALTER TABLE boq_items
    ALTER COLUMN price_difference_percent TYPE DECIMAL(8, 2);

COMMENT ON COLUMN boq_items.price_difference_percent IS
    'Percentage difference contractor vs market. Wide range tolerated: bad matches can be off by 1000s of percent; match quality filtering is the consumer''s job.';
