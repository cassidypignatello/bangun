-- ============================================
-- BOQ UPLOAD FEATURE - DATABASE SCHEMA
-- Migration: 007_create_boq_tables.sql
-- Run in: Supabase SQL Editor
-- ============================================

-- ============================================
-- ENUM TYPES
-- ============================================

-- BoQ job processing states
CREATE TYPE boq_job_status AS ENUM ('pending', 'processing', 'completed', 'failed');

-- File format types
CREATE TYPE boq_file_format AS ENUM ('pdf', 'xlsx', 'xls');

-- Item classification
CREATE TYPE boq_item_type AS ENUM ('material', 'labor', 'equipment', 'unknown');


-- ============================================
-- TABLES
-- ============================================

-- BoQ Jobs Table (tracks upload and processing state)
CREATE TABLE boq_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- User tracking (anonymous until they sign up)
    session_id VARCHAR(100),
    user_id UUID,

    -- File info
    filename VARCHAR(255) NOT NULL,
    file_format boq_file_format NOT NULL,
    file_size_bytes INT,
    file_storage_path TEXT,  -- Supabase Storage path if persisted

    -- Processing state
    status boq_job_status DEFAULT 'pending',
    progress_percent INT DEFAULT 0,
    error_message TEXT,

    -- Extraction metadata
    total_items_extracted INT DEFAULT 0,
    materials_count INT DEFAULT 0,
    labor_count INT DEFAULT 0,
    owner_supply_count INT DEFAULT 0,

    -- Pricing summary
    contractor_total DECIMAL(15, 2),
    market_estimate DECIMAL(15, 2),
    potential_savings DECIMAL(15, 2),

    -- Document metadata (extracted from BoQ header)
    project_name VARCHAR(255),
    contractor_name VARCHAR(255),
    project_location VARCHAR(255),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processing_started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


-- BoQ Items Table (individual line items from the BoQ)
CREATE TABLE boq_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Parent job
    job_id UUID NOT NULL REFERENCES boq_jobs(id) ON DELETE CASCADE,

    -- Original data from BoQ
    section VARCHAR(255),           -- e.g., "PEKERJAAN KERAMIK"
    item_number VARCHAR(20),        -- e.g., "A.1" or "1"
    description TEXT NOT NULL,      -- Original Indonesian text
    unit VARCHAR(50),               -- m2, m1, unit, ls, set, titik
    quantity DECIMAL(12, 4),
    contractor_unit_price DECIMAL(15, 2),
    contractor_total DECIMAL(15, 2),

    -- Classification
    item_type boq_item_type DEFAULT 'unknown',
    is_owner_supply BOOLEAN DEFAULT FALSE,  -- "Supply By Owner" items
    is_existing BOOLEAN DEFAULT FALSE,      -- "use existing" items
    extraction_confidence DECIMAL(4, 3),    -- 0.000 - 1.000

    -- Tokopedia matching
    search_query VARCHAR(255),              -- Normalized search term
    tokopedia_product_name VARCHAR(500),
    tokopedia_price DECIMAL(15, 2),
    tokopedia_url TEXT,
    tokopedia_seller VARCHAR(255),
    tokopedia_seller_location VARCHAR(100),
    tokopedia_rating DECIMAL(2, 1),
    tokopedia_sold_count INT,
    match_confidence DECIMAL(4, 3),         -- 0.000 - 1.000

    -- Calculated fields
    market_unit_price DECIMAL(15, 2),
    market_total DECIMAL(15, 2),
    price_difference DECIMAL(15, 2),        -- contractor - market
    price_difference_percent DECIMAL(5, 2), -- percentage difference

    -- Metadata
    raw_extraction JSONB,           -- Original extracted data for debugging
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


-- ============================================
-- INDEXES
-- ============================================

-- BoQ Jobs indexes
CREATE INDEX idx_boq_jobs_session ON boq_jobs(session_id);
CREATE INDEX idx_boq_jobs_status ON boq_jobs(status);
CREATE INDEX idx_boq_jobs_created ON boq_jobs(created_at DESC);

-- BoQ Items indexes
CREATE INDEX idx_boq_items_job ON boq_items(job_id);
CREATE INDEX idx_boq_items_type ON boq_items(item_type);
CREATE INDEX idx_boq_items_owner_supply ON boq_items(is_owner_supply) WHERE is_owner_supply = TRUE;
CREATE INDEX idx_boq_items_section ON boq_items(section);


-- ============================================
-- TRIGGERS
-- ============================================

-- Auto-update updated_at for boq_jobs
CREATE TRIGGER update_boq_jobs_updated_at
    BEFORE UPDATE ON boq_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Auto-update updated_at for boq_items
CREATE TRIGGER update_boq_items_updated_at
    BEFORE UPDATE ON boq_items
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================
-- ROW LEVEL SECURITY
-- ============================================

ALTER TABLE boq_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE boq_items ENABLE ROW LEVEL SECURITY;

-- BoQ Jobs: Users can view their own jobs
CREATE POLICY "Users can view own boq jobs" ON boq_jobs
    FOR SELECT USING (
        session_id = current_setting('app.session_id', true)
        OR user_id = auth.uid()
    );

-- BoQ Jobs: Allow creating new jobs
CREATE POLICY "Users can create boq jobs" ON boq_jobs
    FOR INSERT WITH CHECK (true);

-- BoQ Jobs: Allow updating own jobs (for status updates)
CREATE POLICY "Users can update own boq jobs" ON boq_jobs
    FOR UPDATE USING (
        session_id = current_setting('app.session_id', true)
        OR user_id = auth.uid()
    );

-- BoQ Items: Users can view items from their jobs
CREATE POLICY "Users can view own boq items" ON boq_items
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM boq_jobs
            WHERE boq_jobs.id = boq_items.job_id
            AND (
                boq_jobs.session_id = current_setting('app.session_id', true)
                OR boq_jobs.user_id = auth.uid()
            )
        )
    );

-- BoQ Items: Allow inserting items (via backend processing)
CREATE POLICY "Service can create boq items" ON boq_items
    FOR INSERT WITH CHECK (true);

-- BoQ Items: Allow updating items (via backend processing)
CREATE POLICY "Service can update boq items" ON boq_items
    FOR UPDATE USING (true);


-- ============================================
-- VERIFICATION
-- ============================================
-- SELECT * FROM boq_jobs LIMIT 1;
-- SELECT * FROM boq_items LIMIT 1;
