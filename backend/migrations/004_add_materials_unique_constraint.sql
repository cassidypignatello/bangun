-- ============================================
-- BALI RENOVATION OS - MATERIALS DEDUPLICATION
-- Migration: 004_add_materials_unique_constraint.sql
-- Purpose: Prevent duplicate materials with case-variant names
-- ============================================

-- Run entire migration in a transaction for atomicity
BEGIN;

-- ============================================
-- STEP 1: CLEANUP - Remove case-variant duplicates FIRST
-- Keeps the row with the most recent price_updated_at
-- If tie, keeps the row with the smallest id (oldest record)
-- IMPORTANT: Skips rows referenced by affiliate_clicks to avoid FK violations
-- ============================================

-- Log duplicates before deletion (for audit purposes)
DO $$
DECLARE
    duplicate_count INTEGER;
    referenced_count INTEGER;
BEGIN
    -- Count duplicate groups
    SELECT COUNT(*) INTO duplicate_count
    FROM (
        SELECT LOWER(name_id) as normalized_name
        FROM materials
        GROUP BY LOWER(name_id)
        HAVING COUNT(*) > 1
    ) dups;

    -- Count materials with FK references (these will be preserved)
    SELECT COUNT(DISTINCT material_id) INTO referenced_count
    FROM affiliate_clicks
    WHERE material_id IS NOT NULL;

    IF duplicate_count > 0 THEN
        RAISE NOTICE 'Found % duplicate material name groups to clean up', duplicate_count;
        RAISE NOTICE '% materials have affiliate_clicks references and will be preserved', referenced_count;
    ELSE
        RAISE NOTICE 'No duplicate materials found - cleanup not needed';
    END IF;
END $$;

-- Delete duplicate rows, keeping the "best" one per LOWER(name_id)
-- Best = most recent price_updated_at, or if tied, lowest id
-- FK-SAFE: Never delete rows referenced by affiliate_clicks
DELETE FROM materials m1
WHERE EXISTS (
    SELECT 1 FROM materials m2
    WHERE LOWER(m1.name_id) = LOWER(m2.name_id)
    AND m1.id != m2.id
    AND (
        -- m2 has more recent price data
        (m2.price_updated_at > m1.price_updated_at)
        -- m2 has price data, m1 doesn't
        OR (m2.price_updated_at IS NOT NULL AND m1.price_updated_at IS NULL)
        -- Same timestamp (including both NULL), keep lower id
        -- IS NOT DISTINCT FROM treats NULL = NULL as true
        OR (
            m2.price_updated_at IS NOT DISTINCT FROM m1.price_updated_at
            AND m2.id < m1.id
        )
    )
)
-- FK-SAFE: Do not delete materials referenced by affiliate_clicks
AND NOT EXISTS (
    SELECT 1 FROM affiliate_clicks ac
    WHERE ac.material_id = m1.id
);

-- Log any remaining duplicates (due to FK protection)
DO $$
DECLARE
    remaining_duplicates INTEGER;
BEGIN
    SELECT COUNT(*) INTO remaining_duplicates
    FROM (
        SELECT LOWER(name_id) as normalized_name
        FROM materials
        GROUP BY LOWER(name_id)
        HAVING COUNT(*) > 1
    ) dups;

    IF remaining_duplicates > 0 THEN
        RAISE WARNING 'WARNING: % duplicate groups remain due to FK references', remaining_duplicates;
        RAISE WARNING 'These duplicates have affiliate_clicks and cannot be auto-deleted';
        RAISE WARNING 'Manual intervention required: merge affiliate_clicks, then re-run migration';
    ELSE
        RAISE NOTICE 'All duplicates successfully cleaned up';
    END IF;
END $$;

-- ============================================
-- STEP 2: CREATE UNIQUE INDEX (now safe - no duplicates)
-- Note: Will fail if FK-protected duplicates remain
-- ============================================

-- Create a unique index on lowercase name_id to prevent duplicates like
-- "Semen Portland" and "semen portland" from coexisting
-- Using a functional index allows case-insensitive uniqueness
CREATE UNIQUE INDEX IF NOT EXISTS idx_materials_name_id_lower_unique
ON materials (LOWER(name_id));

-- ============================================
-- STEP 3: CREATE PERFORMANCE INDEXES
-- ============================================

-- Index on lowercase name_en for faster case-insensitive lookups
CREATE INDEX IF NOT EXISTS idx_materials_name_en_lower
ON materials (LOWER(name_en));

-- GIN index on aliases for faster array containment queries
-- This speeds up the alias-based material lookup
CREATE INDEX IF NOT EXISTS idx_materials_aliases_gin
ON materials USING GIN (aliases);

-- Index on category for filtered queries
CREATE INDEX IF NOT EXISTS idx_materials_category
ON materials (category);

-- Index on price_updated_at for cache freshness queries
CREATE INDEX IF NOT EXISTS idx_materials_price_updated_at
ON materials (price_updated_at);

COMMIT;

-- ============================================
-- MANUAL CLEANUP (if FK-protected duplicates remain)
-- ============================================

-- Step 1: Identify duplicates with FK references
-- SELECT
--     LOWER(m.name_id) as normalized_name,
--     m.id,
--     m.name_id,
--     m.price_updated_at,
--     COUNT(ac.id) as affiliate_click_count
-- FROM materials m
-- LEFT JOIN affiliate_clicks ac ON ac.material_id = m.id
-- WHERE LOWER(m.name_id) IN (
--     SELECT LOWER(name_id) FROM materials
--     GROUP BY LOWER(name_id) HAVING COUNT(*) > 1
-- )
-- GROUP BY m.id, m.name_id, m.price_updated_at
-- ORDER BY normalized_name, m.price_updated_at DESC NULLS LAST;

-- Step 2: Migrate affiliate_clicks to the canonical material
-- UPDATE affiliate_clicks
-- SET material_id = '<canonical_material_id>'
-- WHERE material_id = '<duplicate_material_id>';

-- Step 3: Delete the now-unreferenced duplicate
-- DELETE FROM materials WHERE id = '<duplicate_material_id>';

-- ============================================
-- VERIFICATION QUERIES (run manually after migration)
-- ============================================

-- Verify no duplicates remain:
-- SELECT LOWER(name_id), COUNT(*) FROM materials GROUP BY LOWER(name_id) HAVING COUNT(*) > 1;

-- Verify unique index exists:
-- SELECT indexname FROM pg_indexes WHERE tablename = 'materials' AND indexname LIKE '%unique%';

-- Check index usage:
-- SELECT indexrelname, idx_scan, idx_tup_read FROM pg_stat_user_indexes WHERE relname = 'materials';
