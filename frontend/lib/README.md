# Frontend API Integration

Type-safe API client and React hooks for the Bangun backend.

## Architecture

```
lib/
├── api/                  # API client modules
│   ├── client.ts        # Core HTTP client with error handling
│   ├── workers.ts       # Worker search endpoints
│   ├── payments.ts      # Payment & unlock endpoints
│   ├── estimates.ts     # Cost estimation endpoints
│   ├── materials.ts     # Materials pricing endpoints
│   └── index.ts         # Exports
├── hooks/               # React hooks for data fetching
│   ├── useWorkerSearch.ts
│   ├── useWorkerDetails.ts
│   ├── useEstimate.ts
│   ├── usePayment.ts
│   └── index.ts
├── types/               # TypeScript type definitions
│   ├── worker.ts        # Worker schemas
│   ├── payment.ts       # Payment schemas
│   ├── estimate.ts      # Estimate schemas
│   └── index.ts
└── config.ts            # Environment configuration
```

## Quick Start

### 1. Environment Setup

Copy `.env.local.example` to `.env.local`:

```bash
cp .env.local.example .env.local
```

Update with your backend URL:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 2. Using API Client (Low-level)

```typescript
import { workersApi } from "@/lib/api";

const response = await workersApi.search({
  project_type: "pool_construction",
  location: "Canggu",
  min_trust_score: 60,
  max_results: 5,
});

if (response.error) {
  console.error(response.error.message);
} else {
  console.log(response.data.workers);
}
```

### 3. Using React Hooks (Recommended)

```typescript
import { useWorkerSearch } from "@/lib/hooks";

function WorkerSearchComponent() {
  const { data, loading, error, search } = useWorkerSearch();

  const handleSearch = () => {
    search({
      project_type: "bathroom_renovation",
      location: "Ubud",
    });
  };

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      <button onClick={handleSearch}>Search Workers</button>
      {data?.workers.map(worker => (
        <div key={worker.id}>{worker.preview_name}</div>
      ))}
    </div>
  );
}
```

## API Modules

### Workers API

```typescript
import { workersApi } from "@/lib/api";

// Search workers
const searchResult = await workersApi.search({
  project_type: "pool_construction",
  location: "Canggu",
  min_trust_score: 40,
  max_results: 10,
});

// Get worker preview (masked contact)
const preview = await workersApi.getPreview("worker-id");

// Get full details (requires unlock)
const details = await workersApi.getDetails("worker-id");
```

### Payments API

```typescript
import { paymentsApi, PaymentMethod } from "@/lib/api";

// Initiate unlock payment
const unlockResult = await paymentsApi.unlockWorker({
  worker_id: "worker-id",
  payment_method: PaymentMethod.GOPAY,
  return_url: "https://app.example.com/workers/worker-id",
});

// Check unlock status
const status = await paymentsApi.checkUnlockStatus("worker-id");
```

### Estimates API

```typescript
import { estimatesApi } from "@/lib/api";

// Create estimate
const estimate = await estimatesApi.create({
  project_type: "bathroom_renovation",
  area_sqm: 10,
  location: "Canggu",
});

// Poll status
const status = await estimatesApi.getStatus("estimate-id");

// Get full details
const details = await estimatesApi.getDetails("estimate-id");
```

### Materials API

```typescript
import { materialsApi } from "@/lib/api";

// List materials
const materials = await materialsApi.list({
  category: "tiles",
  search: "ceramic",
});

// Get price history
const history = await materialsApi.getHistory("material-id");
```

## React Hooks

### useWorkerSearch

```typescript
const { data, loading, error, search, reset } = useWorkerSearch();

// Trigger search
await search({
  project_type: "pool_construction",
  location: "Canggu",
});

// Reset state
reset();
```

### useWorkerDetails

```typescript
const { preview, fullDetails, loading, error, refetch } = useWorkerDetails({
  workerId: "worker-id",
  fetchFull: false, // true to fetch full details
});
```

### useEstimate

```typescript
const { estimate, loading, error, progress, createEstimate, reset } = useEstimate();

// Create and auto-poll
await createEstimate({
  project_type: "bathroom_renovation",
  area_sqm: 10,
});

// Progress is updated automatically (0-100)
console.log(progress);
```

### usePayment

```typescript
const { unlockResponse, loading, error, initiateUnlock, checkUnlockStatus } = usePayment();

// Initiate payment (redirects to payment page)
await initiateUnlock("worker-id", PaymentMethod.GOPAY);

// Check if already unlocked
const isUnlocked = await checkUnlockStatus("worker-id");
```

## Type Safety

All API responses are fully typed:

```typescript
import type { WorkerPreview, TrustLevel } from "@/lib/types";

const worker: WorkerPreview = {
  id: "abc-123",
  preview_name: "P██ W████'s Pool Service",
  trust_score: {
    total_score: 87,
    trust_level: TrustLevel.VERIFIED,
    breakdown: {
      source: 24,
      reviews: 22,
      rating: 20,
      verification: 11,
      freshness: 10,
    },
    source_tier: "google_maps",
    review_count: 67,
    rating: 4.8,
  },
  location: "Canggu",
  specializations: ["pool"],
  preview_review: "Excellent work...",
  photos_count: 15,
  opening_hours: "Mon-Sat 8AM-5PM",
  price_idr_per_day: null,
  contact_locked: true,
  unlock_price_idr: 50000,
};
```

## Error Handling

All API methods return `ApiResponse<T>`:

```typescript
interface ApiResponse<T> {
  data?: T;
  error?: ApiError;
}

interface ApiError {
  message: string;
  code?: string;
  details?: unknown;
}
```

Example:

```typescript
const response = await workersApi.search(request);

if (response.error) {
  // Handle error
  console.error(response.error.message);
  if (response.error.code === "HTTP_404") {
    // Specific error handling
  }
} else if (response.data) {
  // Handle success
  console.log(response.data);
}
```

## Testing

Visit `/test-api` in your browser to test all API endpoints interactively:

```
http://localhost:3000/test-api
```

## Backend Integration

### CORS Configuration

Ensure backend allows frontend origin. In FastAPI (`backend/app/main.py`):

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### API Base URL

Development: `http://localhost:8000`
Production: Set via `NEXT_PUBLIC_API_URL` environment variable

## Best Practices

1. **Always use hooks in components** - They handle loading/error states
2. **Check for errors** - API calls can fail, always handle the error case
3. **Type safety** - Import types from `@/lib/types` for autocomplete
4. **Environment variables** - Never hardcode API URLs, use config
5. **Polling** - Use `useEstimate` hook for async operations, it handles polling automatically

## Troubleshooting

### API calls fail with CORS errors

- Check backend CORS middleware configuration
- Verify `NEXT_PUBLIC_API_URL` matches backend URL
- Ensure backend is running on expected port

### Types don't match backend

- Types are synchronized with backend schemas in `backend/app/schemas/`
- If backend changes, update corresponding TypeScript types in `lib/types/`

### Environment variables not working

- Next.js requires `NEXT_PUBLIC_` prefix for client-side variables
- Restart dev server after changing `.env.local`
- Check `.env.local` is not committed (it's in `.gitignore`)
