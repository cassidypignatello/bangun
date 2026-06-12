-- Migration 011: add priced_contractor_total to boq_jobs
--
-- Adds the contractor-quote subtotal computed over the same item-subset used
-- for market_estimate (items with a market_total).  Keeping both numerator and
-- denominator of the savings calculation on the same set prevents the
-- apples-vs-oranges savings figure that was present before this fix.
--
-- NULL when no items were priced (same semantics as market_estimate).

ALTER TABLE boq_jobs
    ADD COLUMN IF NOT EXISTS priced_contractor_total DECIMAL(15, 2);

COMMENT ON COLUMN boq_jobs.priced_contractor_total IS
    'Sum of contractor_total over only the items that received a market price. '
    'Used as the denominator for savings_percent so the comparison is symmetric. '
    'NULL when priced_count = 0.';
