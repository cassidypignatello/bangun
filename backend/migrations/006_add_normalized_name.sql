-- Migration: 006_add_normalized_name.sql
-- Purpose: Add normalized_name column for deterministic cache lookups
-- Date: 2025-12-27

-- Add normalized_name column for consistent cache matching
-- This column stores a canonical form of the material name that handles:
-- - Case variations (Semen Portland vs semen portland)
-- - Spacing differences (50 kg vs 50kg)
-- - Word order variations (Portland Semen vs Semen Portland)
-- - Special characters removed

ALTER TABLE materials
    ADD COLUMN IF NOT EXISTS normalized_name TEXT;

-- Add comment for documentation
COMMENT ON COLUMN materials.normalized_name IS 'Canonicalized material name for cache lookup: lowercase, sorted words, units attached to numbers';

-- Create index for fast exact-match lookups on normalized_name
CREATE INDEX IF NOT EXISTS idx_materials_normalized_name ON materials (normalized_name)
    WHERE normalized_name IS NOT NULL;
