-- Migration 003: Worker Discovery System
-- Creates tables for worker/contractor profiles from Google Maps scraping
-- Run this in Supabase SQL Editor

-- ============================================================================
-- WORKERS TABLE
-- ============================================================================
-- Stores contractor/worker profiles from multiple sources (primarily Google Maps)
-- with trust scoring and contact information

CREATE TABLE IF NOT EXISTS workers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    name VARCHAR(255),  -- Personal name (for individuals)
    business_name VARCHAR(255) NOT NULL,  -- Business/company name (primary)
    source_tier VARCHAR(50) NOT NULL,  -- 'google_maps', 'olx', 'manual', 'platform'

    -- Contact Information (will be encrypted in application layer)
    phone VARCHAR(100),
    whatsapp VARCHAR(100),
    email VARCHAR(255),
    website VARCHAR(500),

    -- Location
    location VARCHAR(255),  -- General area (e.g., "Canggu", "Ubud")
    address TEXT,  -- Full address
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),

    -- Google Maps Data
    gmaps_place_id VARCHAR(255) UNIQUE,  -- Google Maps unique identifier
    gmaps_rating DECIMAL(3, 2),  -- 0.0-5.0
    gmaps_review_count INTEGER DEFAULT 0,
    gmaps_photos_count INTEGER DEFAULT 0,
    gmaps_url TEXT,
    gmaps_categories TEXT[],  -- Array of category strings

    -- OLX Data (if we add OLX scraping later)
    olx_listing_id VARCHAR(255) UNIQUE,
    olx_listing_age_days INTEGER,
    olx_price_idr INTEGER,  -- Daily/hourly rate from listing
    olx_url TEXT,

    -- Trust Scoring (cached, recalculated periodically)
    trust_score INTEGER CHECK (trust_score >= 0 AND trust_score <= 100),
    trust_level VARCHAR(20),  -- 'VERIFIED', 'HIGH', 'MEDIUM', 'LOW'
    trust_score_breakdown JSONB,  -- Detailed breakdown of scoring components
    last_score_calculated_at TIMESTAMPTZ,

    -- Platform Data (from our system, after worker starts using platform)
    platform_jobs_completed INTEGER DEFAULT 0,
    platform_rating DECIMAL(3, 2),

    -- Specializations
    specializations TEXT[],  -- ['pool', 'bathroom', 'kitchen', 'general']

    -- Business Hours
    opening_hours TEXT,  -- Formatted string like "Mon-Sat 8AM-5PM"

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_scraped_at TIMESTAMPTZ,  -- When data was last refreshed from source
    is_active BOOLEAN DEFAULT TRUE,  -- Soft delete flag

    -- Preview review (top review snippet for preview display)
    preview_review TEXT,

    -- Constraints
    CONSTRAINT valid_source_tier CHECK (source_tier IN ('google_maps', 'olx', 'manual', 'platform')),
    CONSTRAINT valid_trust_level CHECK (trust_level IN ('VERIFIED', 'HIGH', 'MEDIUM', 'LOW') OR trust_level IS NULL)
);

-- ============================================================================
-- WORKER REVIEWS TABLE
-- ============================================================================
-- Stores individual reviews scraped from Google Maps or submitted on platform

CREATE TABLE IF NOT EXISTS worker_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_id UUID REFERENCES workers(id) ON DELETE CASCADE,

    -- Review Source
    source VARCHAR(50) NOT NULL,  -- 'google_maps', 'platform'
    source_review_id VARCHAR(255),  -- External review ID (for deduplication)

    -- Review Content
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    review_text TEXT,
    reviewer_name VARCHAR(255),
    reviewer_photo_url TEXT,
    review_date DATE,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT valid_source CHECK (source IN ('google_maps', 'platform', 'olx')),
    UNIQUE (worker_id, source, source_review_id)  -- Prevent duplicate imports
);

-- ============================================================================
-- WORKER UNLOCK TRACKING TABLE
-- ============================================================================
-- Tracks which users have unlocked which workers (after payment)

CREATE TABLE IF NOT EXISTS worker_unlocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Unlock Details
    worker_id UUID REFERENCES workers(id) ON DELETE CASCADE,
    user_email VARCHAR(255) NOT NULL,  -- User who unlocked (or payment transaction ID)
    payment_id UUID,  -- References payments table if integrated

    -- Pricing
    unlock_price_idr INTEGER NOT NULL DEFAULT 50000,

    -- Metadata
    unlocked_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    UNIQUE (worker_id, user_email)  -- Prevent duplicate unlocks by same user
);

-- ============================================================================
-- SCRAPE JOBS TABLE (ENHANCEMENT)
-- ============================================================================
-- Note: scrape_jobs table already exists from Migration 001 with ENUM types
-- The existing table already supports worker scraping with:
--   - job_type: scrape_type ENUM ('materials', 'workers_olx', 'workers_gmaps')
--   - status: scrape_status ENUM ('pending', 'running', 'completed', 'failed')
-- No changes needed to scrape_jobs table for worker discovery feature

-- ============================================================================
-- INDEXES
-- ============================================================================
-- Optimized for common query patterns

-- Workers table indexes
CREATE INDEX IF NOT EXISTS idx_workers_source_tier ON workers(source_tier);
CREATE INDEX IF NOT EXISTS idx_workers_trust_score ON workers(trust_score DESC) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_workers_trust_level ON workers(trust_level) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_workers_location ON workers(location);
CREATE INDEX IF NOT EXISTS idx_workers_specializations ON workers USING GIN(specializations);
CREATE INDEX IF NOT EXISTS idx_workers_gmaps_place_id ON workers(gmaps_place_id) WHERE gmaps_place_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workers_olx_listing_id ON workers(olx_listing_id) WHERE olx_listing_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workers_active ON workers(is_active, trust_score DESC);

-- Composite index for common search pattern (location + specialization + trust)
CREATE INDEX IF NOT EXISTS idx_workers_search ON workers(location, trust_score DESC)
    WHERE is_active = TRUE AND trust_score >= 40;

-- Reviews table indexes
CREATE INDEX IF NOT EXISTS idx_worker_reviews_worker_id ON worker_reviews(worker_id);
CREATE INDEX IF NOT EXISTS idx_worker_reviews_source ON worker_reviews(source);
CREATE INDEX IF NOT EXISTS idx_worker_reviews_date ON worker_reviews(review_date DESC);

-- Unlocks table indexes
CREATE INDEX IF NOT EXISTS idx_worker_unlocks_worker_id ON worker_unlocks(worker_id);
CREATE INDEX IF NOT EXISTS idx_worker_unlocks_user_email ON worker_unlocks(user_email);
CREATE INDEX IF NOT EXISTS idx_worker_unlocks_unlocked_at ON worker_unlocks(unlocked_at DESC);

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Function to update updated_at timestamp automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at on workers table
DROP TRIGGER IF EXISTS update_workers_updated_at ON workers;
CREATE TRIGGER update_workers_updated_at
    BEFORE UPDATE ON workers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- ROW LEVEL SECURITY (Optional, enable if using Supabase auth)
-- ============================================================================

-- Disable RLS for service key access (backend has full access)
-- Enable RLS if you want frontend direct access with user authentication

-- ALTER TABLE workers ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE worker_reviews ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE worker_unlocks ENABLE ROW LEVEL SECURITY;

-- Example policy for public read access to active workers:
-- CREATE POLICY "Workers are viewable by everyone"
--     ON workers FOR SELECT
--     USING (is_active = TRUE);

-- Example policy for unlock tracking:
-- CREATE POLICY "Users can view their own unlocks"
--     ON worker_unlocks FOR SELECT
--     USING (user_email = current_user);

-- ============================================================================
-- SAMPLE DATA (Optional, for testing)
-- ============================================================================

-- Uncomment to insert sample worker for testing
-- INSERT INTO workers (
--     business_name, source_tier, location, specializations,
--     gmaps_place_id, gmaps_rating, gmaps_review_count, gmaps_photos_count,
--     trust_score, trust_level, phone, website, opening_hours
-- ) VALUES (
--     'Pak Wayan Pool Service', 'google_maps', 'Canggu', ARRAY['pool'],
--     'ChIJN1t_tDetest123', 4.8, 67, 15,
--     84, 'VERIFIED', '+62361234567', 'https://pakwayanpool.com', 'Mon-Sat 8AM-5PM'
-- );

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
-- Next steps:
-- 1. Run this SQL in Supabase SQL Editor
-- 2. Verify tables created: SELECT * FROM workers LIMIT 1;
-- 3. Check indexes: SELECT * FROM pg_indexes WHERE tablename IN ('workers', 'worker_reviews', 'worker_unlocks');
-- 4. Proceed with backend Supabase integration code
