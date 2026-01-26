# Bangun - Backend API

AI-powered construction cost estimation for Indonesia.

## Tech Stack

- **Framework**: FastAPI 0.109+
- **Database**: Supabase (PostgreSQL)
- **AI**: OpenAI GPT-4o-mini with prompt caching
- **Scraping**: Apify (Tokopedia product scraper)
- **Payments**: Midtrans payment gateway
- **Monitoring**: Sentry error tracking

## Features

- **Cost Estimation**: AI-powered Bill of Materials generation
- **Real-time Pricing**: Tokopedia scraping with intelligent caching
- **Worker Discovery**: Trusted contractor profiles with verification
- **Payment Processing**: Secure worker detail unlock via Midtrans
- **Semantic Matching**: Two-tier material matching (exact + fuzzy)

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Pydantic Settings
│   ├── routes/              # API endpoints
│   │   ├── estimates.py     # Cost estimation
│   │   ├── workers.py       # Worker discovery
│   │   ├── payments.py      # Payment processing
│   │   ├── materials.py     # Material catalog
│   │   └── health.py        # Health checks
│   ├── services/            # Business logic
│   │   ├── bom_generator.py
│   │   ├── semantic_matcher.py
│   │   ├── trust_calculator.py
│   │   └── price_engine.py
│   ├── schemas/             # Pydantic models
│   ├── integrations/        # External services
│   │   ├── supabase.py
│   │   ├── openai_client.py
│   │   ├── apify.py
│   │   └── midtrans.py
│   └── middleware/          # FastAPI middleware
├── tests/                   # Test suite
└── requirements.txt
```

## Setup

### 1. Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required variables:
- `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`
- `OPENAI_API_KEY`
- `APIFY_TOKEN`
- `MIDTRANS_SERVER_KEY` and `MIDTRANS_CLIENT_KEY`
- `FIELD_ENCRYPTION_KEY` (generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- `SENTRY_DSN` (optional)

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run Development Server

```bash
uvicorn app.main:app --reload --port 8000
```

API will be available at `http://localhost:8000`

Documentation at `http://localhost:8000/docs` (when `DEBUG=true`)

## API Endpoints

### Cost Estimation

**POST /estimate**
- Create new cost estimate (returns 202 Accepted)
- Background processing with BOM generation
- Request body: `ProjectInput` schema

**GET /estimate/{id}/status**
- Check estimate processing status
- Returns progress percentage

**GET /estimate/{id}**
- Get complete estimate with BOM breakdown
- Includes material prices and labor costs

### Worker Discovery

**GET /workers/preview/{project_type}**
- Get worker previews for project type
- Returns masked details (pre-unlock)
- Sorted by trust score

**GET /workers/{worker_id}/preview**
- Get single worker preview

### Payments

**POST /unlock**
- Create payment to unlock worker details
- Returns Midtrans payment URL
- Fixed price: 50,000 IDR

**POST /webhooks/midtrans**
- Midtrans webhook handler
- Verifies SHA512 signature
- Updates transaction status

### Materials

**GET /materials**
- Browse material catalog
- Optional search parameter

**GET /materials/{name}/history**
- Price history for specific material

### Health

**GET /health** - Basic health check
**GET /health/ready** - Readiness check with dependencies
**GET /health/metrics** - Application metrics

## Key Features

### Prompt Caching

OpenAI system prompt is defined as a constant in `openai_client.py` for automatic caching:

```python
SYSTEM_PROMPT = """You are an expert construction cost estimator..."""
```

Saves ~50% on token costs for repeated requests.

### Two-Tier Semantic Matching

1. **Exact Match**: High-confidence (>0.95) from historical data
2. **Fuzzy Match**: Lower threshold (>0.75) with SequenceMatcher
3. **Fallback**: Real-time Tokopedia scraping

### Webhook Signature Verification

Midtrans webhooks verified with SHA512:

```python
SHA512(order_id + status_code + gross_amount + server_key)
```

### Rate Limiting

- Standard: 60/minute
- Heavy: 10/minute (estimate creation)
- Light: 100/minute (status checks)

## Testing

Run tests with pytest:

```bash
pytest tests/ -v
```

## Production Deployment

### Environment Configuration

Set `ENV=production` and `DEBUG=false` in production.

### Database Migrations

Database schema should be set up in Supabase:

**Tables needed:**
- `projects` - Cost estimations and project data
- `materials` - Construction materials catalog with pricing
- `workers` - Contractor profiles with trust scores
- `payments` - Midtrans payment records
- `affiliate_clicks` - Revenue tracking
- `scrape_jobs` - Apify job tracking

### Monitoring

Sentry is configured for error tracking. Set `SENTRY_DSN` to enable.

### Security

- Rate limiting enabled by default
- CORS configured for specific origins
- Webhook signature verification
- Field encryption for sensitive data

## Architecture Decisions

### Async Processing

Estimate generation uses FastAPI BackgroundTasks for async processing:
- Returns 202 immediately
- Processing happens in background
- Client polls status endpoint

### Caching Strategy

Three-tier caching:
1. Historical exact match (instant)
2. Historical fuzzy match (fast)
3. Real-time scraping (slow, cached for future)

### Trust Scoring

Weighted formula:
- Project count: 20%
- Average rating: 30%
- License verification: 15%
- Insurance verification: 15%
- Background check: 10%
- Years experience: 10%

## Development

### Code Style

- Type hints required
- Docstrings for all public functions
- Async/await patterns
- Pydantic for validation

### Adding New Endpoints

1. Create schema in `app/schemas/`
2. Add business logic in `app/services/`
3. Create route in `app/routes/`
4. Include router in `app/main.py`

### Adding New Integrations

1. Create client in `app/integrations/`
2. Add configuration to `app/config.py`
3. Add to `.env.example`

## License

Proprietary - Bangun
