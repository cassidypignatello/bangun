-- Migration: 005_add_material_seller_fields.sql
-- Purpose: Add seller quality and location fields to materials table for enhanced caching
-- Date: 2025-12-24

-- Add fields to cache seller quality metrics from Tokopedia scraper (fatihtahta/tokopedia-scraper)
-- These fields capture aggregated seller data from scraped listings

ALTER TABLE materials
    ADD COLUMN IF NOT EXISTS rating_avg REAL,
    ADD COLUMN IF NOT EXISTS rating_sample_size INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS count_sold_total INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS seller_location TEXT,
    ADD COLUMN IF NOT EXISTS seller_tier TEXT;

-- Add comments for documentation
COMMENT ON COLUMN materials.rating_avg IS 'Average product rating from scraped listings (0.0-5.0)';
COMMENT ON COLUMN materials.rating_sample_size IS 'Number of rated products used to calculate rating_avg';
COMMENT ON COLUMN materials.count_sold_total IS 'Total units sold across all scraped listings';
COMMENT ON COLUMN materials.seller_location IS 'Most common seller location from scraped results';
COMMENT ON COLUMN materials.seller_tier IS 'Seller quality tier: official_store, power_merchant, regular';

-- Create index for filtering by seller tier (useful for quality-filtered queries)
CREATE INDEX IF NOT EXISTS idx_materials_seller_tier ON materials (seller_tier)
    WHERE seller_tier IS NOT NULL;
