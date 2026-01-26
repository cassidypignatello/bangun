# Bangun

**Build smarter.** AI-powered construction cost estimation for Indonesia.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-15-black?style=flat-square&logo=next.js)](https://nextjs.org)
[![Python](https://img.shields.io/badge/Python-3.12-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178c6?style=flat-square&logo=typescript&logoColor=white)](https://typescriptlang.org)

> **Bangun** (Indonesian: *to build*) — Know your costs before you build.

## Overview

Bangun helps homeowners and property developers estimate construction costs with AI-powered Bill of Materials (BOM) generation and real-time pricing from Indonesian marketplaces. Compare contractor quotes against fair market prices.

### Key Features

- **AI Cost Estimation** — GPT-4o-mini generates detailed material lists with quantities from project descriptions
- **Real-time Pricing** — Live Tokopedia scraping via Apify with intelligent 3-tier caching
- **Semantic Matching** — Two-tier material matching (exact + fuzzy) for accurate price lookups
- **Worker Discovery** — Trusted contractor profiles with verification and trust scoring
- **Payment Processing** — Midtrans integration for Indonesian payment methods

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Frontend                                   │
│                    Next.js 15 + React 19                            │
│                    TailwindCSS + TypeScript                         │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ REST API
┌─────────────────────────────▼───────────────────────────────────────┐
│                           Backend                                    │
│                     FastAPI + Python 3.12                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Routes     │  │   Services   │  │ Integrations │              │
│  │  estimates   │  │ bom_generator│  │   supabase   │              │
│  │  workers     │  │ price_engine │  │   openai     │              │
│  │  payments    │  │ semantic_    │  │   apify      │              │
│  │  materials   │  │   matcher    │  │   midtrans   │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   Supabase    │    │    OpenAI     │    │    Apify      │
│  PostgreSQL   │    │  GPT-4o-mini  │    │   Tokopedia   │
│    + Auth     │    │  BOM Gen      │    │    Scraper    │
└───────────────┘    └───────────────┘    └───────────────┘
```

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- Supabase account
- OpenAI API key
- Apify token
- Midtrans account (for payments)

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run development server
uvicorn app.main:app --reload --port 8000
```

API documentation available at `http://localhost:8000/docs`

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.local.example .env.local
# Set NEXT_PUBLIC_API_URL=http://localhost:8000

# Run development server
npm run dev
```

Application available at `http://localhost:3000`

## Project Structure

```
bangun/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── routes/         # API endpoints
│   │   ├── services/       # Business logic
│   │   ├── schemas/        # Pydantic models
│   │   ├── integrations/   # External services
│   │   └── middleware/     # FastAPI middleware
│   ├── tests/              # Test suite
│   └── migrations/         # Database migrations
│
├── frontend/               # Next.js frontend
│   ├── app/               # App router pages
│   ├── components/        # React components
│   └── lib/               # API client & hooks
│       ├── api/           # Type-safe API client
│       ├── hooks/         # React data hooks
│       └── types/         # TypeScript types
│
└── docs/                  # Documentation
    └── architecture/      # Architecture docs
```

## API Endpoints

### Cost Estimation

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/estimate` | Create cost estimate (async, returns 202) |
| `GET` | `/estimate/{id}/status` | Check processing status |
| `GET` | `/estimate/{id}` | Get complete estimate with BOM |

### Materials & Pricing

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/materials/price` | Single item price lookup |
| `POST` | `/api/materials/prices` | Batch price lookup (up to 20) |
| `GET` | `/materials` | Browse material catalog |
| `GET` | `/materials/{name}/history` | Price history |

### Worker Discovery

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/workers/preview/{project_type}` | Search workers (masked) |
| `GET` | `/workers/{id}/preview` | Worker preview |

### Payments

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/unlock` | Create worker unlock payment |
| `POST` | `/webhooks/midtrans` | Payment webhook |

## How It Works

### Cost Estimation Flow

```
1. User describes project (e.g., "10m² bathroom renovation in Canggu")
                              │
                              ▼
2. GPT-4o-mini generates Bill of Materials with quantities
   └── Ceramic tiles: 12m², Grout: 5kg, Waterproofing: 15L...
                              │
                              ▼
3. Semantic matcher finds prices from cache or marketplace
   ├── Cache HIT  → Return instantly (free)
   └── Cache MISS → Scrape Tokopedia → Cache for future
                              │
                              ▼
4. Return itemized estimate with marketplace links
```

### Price Caching Strategy

| Tier | Source | Speed | Cost |
|------|--------|-------|------|
| 1 | In-memory cache (60s TTL) | Instant | Free |
| 2 | Database cache (7-day freshness) | Fast | Free |
| 3 | Live Apify scraping | ~5-10s | ~$0.13/run |

### Trust Scoring Formula

Worker trust scores are calculated using weighted factors:

| Factor | Weight |
|--------|--------|
| Project count | 20% |
| Average rating | 30% |
| License verification | 15% |
| Insurance verification | 15% |
| Background check | 10% |
| Years experience | 10% |

## Tech Stack

### Backend

- **Framework**: FastAPI 0.109+
- **Language**: Python 3.12
- **Database**: Supabase (PostgreSQL)
- **AI**: OpenAI GPT-4o-mini with prompt caching
- **Scraping**: Apify (Tokopedia)
- **Payments**: Midtrans
- **Monitoring**: Sentry

### Frontend

- **Framework**: Next.js 15 (App Router)
- **UI**: React 19 + TailwindCSS
- **Language**: TypeScript 5.7
- **State**: React hooks + API client

## Environment Variables

### Backend (`.env`)

```bash
# Database
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_KEY=your_service_key

# AI
OPENAI_API_KEY=your_openai_key

# Scraping
APIFY_TOKEN=your_apify_token

# Payments
MIDTRANS_SERVER_KEY=your_server_key
MIDTRANS_CLIENT_KEY=your_client_key

# Security
FIELD_ENCRYPTION_KEY=your_fernet_key

# Monitoring (optional)
SENTRY_DSN=your_sentry_dsn
```

### Frontend (`.env.local`)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Development

### Running Tests

```bash
# Backend
cd backend
pytest tests/ -v

# Frontend
cd frontend
npm run lint
```

### Code Style

- **Backend**: Type hints required, async/await patterns, Pydantic validation
- **Frontend**: TypeScript strict mode, ESLint + Prettier

## Rate Limits

| Tier | Limit | Endpoints |
|------|-------|-----------|
| Standard | 60/min | General API |
| Heavy | 10/min | Estimate creation |
| Light | 100/min | Status checks |

## Security

- Webhook signature verification (SHA512)
- Field encryption for sensitive data (Fernet)
- Rate limiting on all endpoints
- CORS configured for specific origins

## Documentation

- [Backend README](./backend/README.md) — API details, setup, endpoints
- [Frontend API Integration](./frontend/lib/README.md) — Type-safe client usage

## License

Proprietary - Bangun
