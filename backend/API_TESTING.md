# API Testing Guide

Comprehensive testing strategy for Bangun backend API endpoints.

## Testing Levels

### 1. Unit Tests (`tests/`)
**Status**: ✅ 39 tests passing (63% coverage)

Run with:
```bash
python3 -m pytest tests/ -v --cov=app
```

Coverage includes:
- Health/readiness endpoints
- Semantic matching algorithms
- Trust score calculations
- Supabase CRUD operations

### 2. Integration Tests (`scripts/test_*_live.py`)
**Status**: ✅ All components validated

Tests with real external APIs:

#### OpenAI BOM Generation
```bash
python3 scripts/test_openai_live.py
```
- Tests GPT-4o-mini BOM generation
- Validates JSON structured output
- Checks material name quality
- Cost: ~$0.03 per test run

#### Tokopedia Price Scraping
```bash
python3 scripts/test_apify_live.py  # Not yet created
```
- Tests Apify actor integration
- Validates product data extraction
- Checks quality filtering
- Cost: ~$0.005 per material

#### E2E Price Engine
```bash
python3 scripts/test_price_engine_e2e.py
```
- Full pipeline: BOM → semantic match → price enrichment
- Tests with predefined BOM (no OpenAI cost)
- Optional live BOM generation test
- Quality filtering validation
- Cost: ~$0.03-0.15 per test run

### 3. API Endpoint Tests (`scripts/test_api_live.py`)
**Status**: ✅ Ready for testing

Prerequisites:
1. Start server: `uvicorn app.main:app --reload`
2. Ensure `.env` credentials configured
3. Database schema initialized

Run with:
```bash
python3 scripts/test_api_live.py
```

Tests:
- POST `/estimates/` - Create cost estimate (202 Accepted)
- GET `/estimates/{id}/status` - Poll processing status
- GET `/estimates/{id}` - Retrieve full estimate
- GET `/materials/` - Search material catalog

Cost: ~$0.03-0.10 per full test run (OpenAI + Apify)

## Test Scenarios

### Scenario 1: Fast Unit Testing (No External APIs)
```bash
python3 -m pytest tests/ -v
```
- Duration: <5 seconds
- Cost: $0
- Coverage: Core logic, database operations

### Scenario 2: Service Integration Testing
```bash
# Test each service independently
python3 scripts/test_openai_live.py      # $0.03
python3 scripts/test_price_engine_e2e.py # $0.05 (predefined BOM)
```
- Duration: ~1-2 minutes
- Cost: ~$0.08
- Coverage: AI, scraping, price aggregation

### Scenario 3: Full API Endpoint Testing
```bash
# Start server first
uvicorn app.main:app --reload &

# Run API tests
python3 scripts/test_api_live.py
```
- Duration: ~2-3 minutes (includes processing time)
- Cost: ~$0.10
- Coverage: Complete API flow, background tasks, status polling

### Scenario 4: Complete Test Suite
```bash
# Run everything in sequence
python3 -m pytest tests/ -v
python3 scripts/test_openai_live.py
python3 scripts/test_price_engine_e2e.py
uvicorn app.main:app --reload &
sleep 5
python3 scripts/test_api_live.py
```
- Duration: ~5 minutes
- Cost: ~$0.20
- Coverage: Everything

## Quality Gates

All tests must pass before deployment:

| Metric | Target | Current |
|--------|--------|---------|
| Unit test pass rate | 100% | ✅ 100% (39/39) |
| Code coverage | >60% | ✅ 63% |
| API response time | <3min | ⏳ Pending |
| Price accuracy | ±20% | ⏳ Pending manual validation |
| Cache hit rate | >50% | ⏳ Pending E2E test |

## Cost Management

Daily testing budget: $5

Recommended testing frequency:
- Unit tests: Every commit (free)
- Integration tests: Before PR (< $0.50)
- API tests: Weekly or major changes (< $1)
- Manual validation: Monthly (< $5)

## Troubleshooting

### Server won't start
```bash
# Check environment variables
cat .env

# Check dependencies
pip install -r requirements.txt

# Check port availability
lsof -i :8000
```

### Tests timing out
```bash
# Increase timeout in test scripts
TIMEOUT = 300  # 5 minutes instead of 180s

# Check API rate limits
# OpenAI: 60 RPM tier-1
# Apify: Check actor concurrency
```

### Price data inconsistency
```bash
# Check database seed data
psql $SUPABASE_URL -c "SELECT COUNT(*) FROM materials;"

# Verify semantic matcher
python3 -c "from app.services.semantic_matcher import match_material; print(match_material('semen portland'))"
```

## Next Steps

1. ✅ Create API test script
2. ⏳ Run live API tests with server
3. ⏳ Add circuit breaker for API failures
4. ⏳ Implement retry logic with exponential backoff
5. ⏳ Add request timeout middleware
6. ⏳ Consider Redis caching for frequent searches

See `WORKFLOW_week2_material_calculator.md` for detailed requirements.
