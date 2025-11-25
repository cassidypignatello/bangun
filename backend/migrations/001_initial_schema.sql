-- ============================================
-- BALI RENOVATION OS - INITIAL DATABASE SCHEMA
-- Migration: 001_initial_schema.sql
-- Run in: Supabase SQL Editor
-- ============================================

-- ============================================
-- PHASE 2: EXTENSIONS
-- ============================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search


-- ============================================
-- PHASE 3: ENUM TYPES
-- ============================================

-- Worker source tracking
CREATE TYPE worker_source AS ENUM ('olx', 'google_maps', 'manual', 'referral');

-- Trust levels for workers
CREATE TYPE trust_level AS ENUM ('low', 'medium', 'high', 'verified');

-- Project lifecycle states
CREATE TYPE project_status AS ENUM ('draft', 'estimated', 'unlocked', 'completed');

-- Payment processing states
CREATE TYPE payment_status AS ENUM ('pending', 'completed', 'failed', 'refunded');

-- Supported payment methods (Midtrans)
CREATE TYPE payment_method AS ENUM ('gopay', 'ovo', 'card', 'bank_transfer');

-- Apify scraping job states
CREATE TYPE scrape_status AS ENUM ('pending', 'running', 'completed', 'failed');

-- Types of scraping jobs
CREATE TYPE scrape_type AS ENUM ('materials', 'workers_olx', 'workers_gmaps');


-- ============================================
-- PHASE 4: TABLES
-- ============================================

-- 4.1 Materials Table
CREATE TABLE materials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    material_code VARCHAR(20) UNIQUE NOT NULL,

    -- Names
    name_id VARCHAR(200) NOT NULL,
    name_en VARCHAR(200) NOT NULL,
    aliases TEXT[] DEFAULT '{}',

    -- Categorization
    category VARCHAR(50) NOT NULL,
    subcategory VARCHAR(50),

    -- Unit & Conversion
    unit VARCHAR(50) NOT NULL,
    unit_conversion JSONB,

    -- Search
    tokopedia_search VARCHAR(200),
    shopee_search VARCHAR(200),

    -- Pricing (cached)
    price_min DECIMAL(12, 2),
    price_max DECIMAL(12, 2),
    price_avg DECIMAL(12, 2),
    price_median DECIMAL(12, 2),
    price_sample_size INT DEFAULT 0,
    price_updated_at TIMESTAMP WITH TIME ZONE,

    -- Affiliate Integration
    tokopedia_affiliate_url TEXT,
    shopee_affiliate_url TEXT,
    affiliate_commission_rate DECIMAL(4, 2),

    -- Metadata
    typical_qty JSONB,
    notes TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


-- 4.2 Workers Table
CREATE TABLE workers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Identity
    name VARCHAR(200) NOT NULL,
    business_name VARCHAR(200),

    -- Source
    source worker_source NOT NULL,
    source_url TEXT,
    source_id VARCHAR(100),

    -- Contact (encrypted in production)
    phone VARCHAR(20),
    whatsapp VARCHAR(20),
    email VARCHAR(200),

    -- Location
    area VARCHAR(100),
    address TEXT,
    coordinates POINT,

    -- Specializations
    specializations TEXT[] DEFAULT '{}',

    -- Trust Metrics (from source)
    gmaps_rating DECIMAL(2, 1),
    gmaps_review_count INT DEFAULT 0,
    gmaps_photos_count INT DEFAULT 0,
    olx_listing_age_days INT,

    -- Calculated Trust Score
    trust_score INT,
    trust_level trust_level,
    trust_breakdown JSONB,
    trust_warnings TEXT[] DEFAULT '{}',

    -- Platform Data
    platform_rating DECIMAL(2, 1),
    platform_review_count INT DEFAULT 0,
    platform_jobs_completed INT DEFAULT 0,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    verified_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    raw_data JSONB,
    last_scraped_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


-- 4.3 Projects Table
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- User (anonymous until they unlock)
    user_id UUID,
    session_id VARCHAR(100),

    -- Project Details
    project_type VARCHAR(100) NOT NULL,
    title VARCHAR(200),
    description TEXT,
    location VARCHAR(100),
    dimensions JSONB,

    -- Estimate
    status project_status DEFAULT 'draft',
    bom JSONB,
    material_total DECIMAL(15, 2),
    labor_estimate JSONB,
    labor_total DECIMAL(15, 2),
    total_estimate DECIMAL(15, 2),
    price_range JSONB,

    -- Matched Workers
    matched_worker_ids UUID[] DEFAULT '{}',

    -- Monetization
    is_unlocked BOOLEAN DEFAULT FALSE,
    unlocked_at TIMESTAMP WITH TIME ZONE,
    unlock_payment_id VARCHAR(100),
    unlock_amount DECIMAL(10, 2),

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


-- 4.4 Payments Table
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    project_id UUID REFERENCES projects(id),
    user_id UUID,

    -- Payment Details
    amount DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'IDR',
    method payment_method,
    status payment_status DEFAULT 'pending',

    -- External Payment Gateway
    gateway_provider VARCHAR(50) DEFAULT 'midtrans',
    gateway_transaction_id VARCHAR(100),
    gateway_response JSONB,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT unique_project_payment UNIQUE (project_id)
);


-- 4.5 Affiliate Clicks Table
CREATE TABLE affiliate_clicks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    project_id UUID REFERENCES projects(id),
    material_id UUID REFERENCES materials(id),
    platform VARCHAR(20) NOT NULL,
    user_session VARCHAR(100),

    -- Click tracking
    clicked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Conversion tracking
    converted BOOLEAN DEFAULT FALSE,
    conversion_amount DECIMAL(12, 2),
    commission_earned DECIMAL(10, 2),
    converted_at TIMESTAMP WITH TIME ZONE
);


-- 4.6 Scrape Jobs Table
CREATE TABLE scrape_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    job_type scrape_type NOT NULL,
    status scrape_status DEFAULT 'pending',

    -- Apify Details
    apify_actor_id VARCHAR(100),
    apify_run_id VARCHAR(100),
    apify_dataset_id VARCHAR(100),

    -- Input/Output
    input_params JSONB,
    items_scraped INT DEFAULT 0,
    errors JSONB,

    -- Timing
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


-- ============================================
-- PHASE 5: INDEXES
-- ============================================

-- Materials indexes
CREATE INDEX idx_materials_aliases ON materials USING GIN (aliases);
CREATE INDEX idx_materials_name_trgm ON materials USING GIN (name_id gin_trgm_ops);
CREATE INDEX idx_materials_category ON materials (category);

-- Workers indexes
CREATE INDEX idx_workers_area ON workers (area);
CREATE INDEX idx_workers_specializations ON workers USING GIN (specializations);
CREATE INDEX idx_workers_trust_score ON workers (trust_score DESC);
CREATE INDEX idx_workers_source ON workers (source);

-- Projects indexes
CREATE INDEX idx_projects_session ON projects (session_id);
CREATE INDEX idx_projects_status ON projects (status);
CREATE INDEX idx_projects_user ON projects (user_id);

-- Affiliate clicks indexes
CREATE INDEX idx_affiliate_clicks_project ON affiliate_clicks(project_id);
CREATE INDEX idx_affiliate_clicks_platform ON affiliate_clicks(platform);
CREATE INDEX idx_affiliate_clicks_converted ON affiliate_clicks(converted);

-- Scrape jobs indexes
CREATE INDEX idx_scrape_jobs_status ON scrape_jobs(status);
CREATE INDEX idx_scrape_jobs_type ON scrape_jobs(job_type);


-- ============================================
-- PHASE 6: FUNCTIONS & TRIGGERS
-- ============================================

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers
CREATE TRIGGER update_materials_updated_at
    BEFORE UPDATE ON materials
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_workers_updated_at
    BEFORE UPDATE ON workers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================
-- PHASE 7: ROW LEVEL SECURITY
-- ============================================

-- Enable RLS
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE affiliate_clicks ENABLE ROW LEVEL SECURITY;

-- Projects: Users can view own projects (by user_id or session_id)
CREATE POLICY "Users can view own projects" ON projects
    FOR SELECT USING (
        user_id = auth.uid()
        OR session_id = current_setting('app.session_id', true)
    );

-- Projects: Users can insert their own projects
CREATE POLICY "Users can create projects" ON projects
    FOR INSERT WITH CHECK (true);

-- Projects: Users can update own projects
CREATE POLICY "Users can update own projects" ON projects
    FOR UPDATE USING (
        user_id = auth.uid()
        OR session_id = current_setting('app.session_id', true)
    );

-- Payments: Users can view own payments
CREATE POLICY "Users can view own payments" ON payments
    FOR SELECT USING (user_id = auth.uid());

-- Payments: Allow insert for payment processing
CREATE POLICY "Service can create payments" ON payments
    FOR INSERT WITH CHECK (true);

-- Affiliate clicks: Allow tracking
CREATE POLICY "Allow affiliate click tracking" ON affiliate_clicks
    FOR INSERT WITH CHECK (true);

CREATE POLICY "Users can view own affiliate clicks" ON affiliate_clicks
    FOR SELECT USING (
        user_session = current_setting('app.session_id', true)
    );


-- ============================================
-- VERIFICATION QUERIES (Run after migration)
-- ============================================

-- Uncomment to verify:
-- SELECT typname FROM pg_type WHERE typtype = 'e';
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
-- SELECT indexname, tablename FROM pg_indexes WHERE schemaname = 'public';
-- SELECT trigger_name, event_object_table FROM information_schema.triggers WHERE trigger_schema = 'public';
-- SELECT tablename, policyname, cmd FROM pg_policies WHERE schemaname = 'public';
