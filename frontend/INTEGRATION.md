# Frontend-Backend Integration Summary

## Overview

Complete type-safe API integration between Next.js 15 frontend and FastAPI backend for Bangun.

## Implementation Status ✅

### 1. Type System
- ✅ TypeScript types matching backend Pydantic schemas
- ✅ Enums for TrustLevel, PaymentStatus, PaymentMethod, EstimateStatus
- ✅ Full type coverage for all API requests/responses
- **Location**: `frontend/lib/types/`

### 2. API Client
- ✅ Generic HTTP client with error handling
- ✅ Consistent `ApiResponse<T>` wrapper pattern
- ✅ Automatic JSON parsing and error transformation
- ✅ Environment-based base URL configuration
- **Location**: `frontend/lib/api/client.ts`

### 3. API Services
- ✅ **Workers API**: Search, preview, full details endpoints
- ✅ **Payments API**: Unlock initiation, status checking
- ✅ **Estimates API**: Create, poll status, get details
- ✅ **Materials API**: List materials, price history
- **Location**: `frontend/lib/api/`

### 4. React Hooks
- ✅ **useWorkerSearch**: Worker search with loading/error states
- ✅ **useWorkerDetails**: Fetch worker preview or full details
- ✅ **useEstimate**: Create estimate with automatic polling
- ✅ **usePayment**: Payment initiation and unlock status
- **Location**: `frontend/lib/hooks/`

### 5. Configuration
- ✅ Environment variables with validation
- ✅ Type-safe config module
- ✅ `.env.local` setup for development
- ✅ `.gitignore` configured for secrets
- **Location**: `frontend/lib/config.ts`, `.env.local.example`

### 6. Testing
- ✅ Test page at `/test-api` for interactive testing
- ✅ Comprehensive README with examples
- **Location**: `frontend/app/test-api/page.tsx`

## Architecture

```
Frontend (Next.js 15 + React 19)
├── lib/
│   ├── types/          TypeScript definitions matching backend schemas
│   ├── api/            API client modules by domain
│   ├── hooks/          React hooks for data fetching
│   └── config.ts       Environment configuration
│
Backend (FastAPI)
├── app/schemas/        Pydantic schemas (source of truth)
├── app/routes/         API endpoints
└── app/main.py         CORS configuration
```

## API Endpoints Mapped

| Endpoint | Frontend Method | Hook |
|----------|----------------|------|
| `POST /workers/search` | `workersApi.search()` | `useWorkerSearch()` |
| `GET /workers/{id}/preview` | `workersApi.getPreview()` | `useWorkerDetails()` |
| `GET /workers/{id}/detail` | `workersApi.getDetails()` | `useWorkerDetails()` |
| `POST /unlock` | `paymentsApi.unlockWorker()` | `usePayment()` |
| `GET /unlock/status` | `paymentsApi.checkUnlockStatus()` | `usePayment()` |
| `POST /estimates` | `estimatesApi.create()` | `useEstimate()` |
| `GET /estimates/{id}/status` | `estimatesApi.getStatus()` | `useEstimate()` |
| `GET /estimates/{id}` | `estimatesApi.getDetails()` | `useEstimate()` |
| `GET /materials` | `materialsApi.list()` | - |
| `GET /materials/{id}/history` | `materialsApi.getHistory()` | - |

## Type Safety Examples

### Worker Search
```typescript
import { useWorkerSearch } from "@/lib/hooks";
import type { WorkerSearchRequest } from "@/lib/types";

const { data, loading, error, search } = useWorkerSearch();

const request: WorkerSearchRequest = {
  project_type: "pool_construction",
  location: "Canggu",
  min_trust_score: 60,
  max_results: 5,
};

await search(request);
// data.workers is fully typed as WorkerPreview[]
```

### Payment Flow
```typescript
import { usePayment, PaymentMethod } from "@/lib/hooks";

const { initiateUnlock, checkUnlockStatus } = usePayment();

// Check if already unlocked
const isUnlocked = await checkUnlockStatus("worker-id");

if (!isUnlocked) {
  // Initiate payment (auto-redirects)
  await initiateUnlock("worker-id", PaymentMethod.GOPAY);
}
```

### Cost Estimation with Polling
```typescript
import { useEstimate } from "@/lib/hooks";

const { estimate, loading, progress, createEstimate } = useEstimate();

await createEstimate({
  project_type: "bathroom_renovation",
  area_sqm: 10,
  location: "Canggu",
});

// Hook automatically polls for completion
// progress: 0-100
// estimate: Full EstimateResponse when complete
```

## Error Handling Pattern

All API calls return `ApiResponse<T>`:

```typescript
const response = await workersApi.search(request);

if (response.error) {
  // Error case
  console.error(response.error.message);
  console.error(response.error.code);
  console.error(response.error.details);
} else if (response.data) {
  // Success case
  const workers = response.data.workers;
}
```

React hooks handle this automatically:

```typescript
const { data, loading, error } = useWorkerSearch();

if (loading) return <Spinner />;
if (error) return <ErrorMessage>{error}</ErrorMessage>;
return <WorkerList workers={data.workers} />;
```

## CORS Configuration

Backend is configured to accept requests from:
- `http://localhost:3000` (Next.js dev server)
- `http://localhost:5173` (Vite fallback)

**Location**: `backend/app/config.py:48`

## Environment Variables

### Development
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_URL=http://localhost:3000
NEXT_PUBLIC_ENVIRONMENT=development
```

### Production
```env
NEXT_PUBLIC_API_URL=https://api.your-domain.com
NEXT_PUBLIC_MIDTRANS_CLIENT_KEY=your_production_client_key
NEXT_PUBLIC_APP_URL=https://your-domain.com
NEXT_PUBLIC_ENVIRONMENT=production
```

## Testing the Integration

### 1. Start Backend
```bash
cd backend
uvicorn app.main:app --reload
```

### 2. Start Frontend
```bash
cd frontend
npm run dev
```

### 3. Test Endpoints
Navigate to: `http://localhost:3000/test-api`

Click buttons to test:
- Worker search API
- Cost estimate API
- View results in real-time

## Next Steps

### Immediate
1. ✅ API integration complete
2. 🔄 Build worker search UI component
3. 🔄 Build cost estimate form component
4. 🔄 Build payment flow components

### Future Enhancements
- [ ] Add request/response caching
- [ ] Implement optimistic updates
- [ ] Add retry logic for failed requests
- [ ] WebSocket support for real-time updates
- [ ] Request deduplication
- [ ] Offline support with service workers

## Key Design Decisions

### 1. ApiResponse Wrapper Pattern
**Decision**: Return `{ data?, error? }` instead of throwing errors
**Rationale**: Forces explicit error handling, prevents uncaught promise rejections, makes error states visible in types

### 2. Separate Hooks per Domain
**Decision**: Domain-specific hooks instead of generic useApi
**Rationale**: Each hook encapsulates domain logic (e.g., polling in useEstimate), better code organization, clearer intent

### 3. TypeScript Enums for String Literals
**Decision**: Use enums for PaymentMethod, TrustLevel, etc.
**Rationale**: IDE autocomplete, type safety, prevents typos, matches backend Python enums

### 4. Automatic Polling in useEstimate
**Decision**: Hook handles polling internally
**Rationale**: Simplifies consumer code, centralizes polling logic, prevents multiple polling implementations

### 5. Singleton API Client
**Decision**: Export instance, not class
**Rationale**: Single source of truth for base URL, easier to mock in tests, consistent configuration

## Documentation

- **API Integration Guide**: `frontend/lib/README.md`
- **Integration Summary**: This file
- **Environment Setup**: `frontend/.env.local.example`
- **Test Page**: `frontend/app/test-api/page.tsx`

## Performance Considerations

### Automatic Optimizations
- JSON parsing only when content-type matches
- Request deduplication via React hook dependencies
- Automatic polling timeout (60s max)
- Progress updates for long-running operations

### Manual Optimizations Needed
- Implement React Query or SWR for caching
- Add request cancellation for unmounted components
- Debounce search inputs
- Virtualize large worker lists

## Troubleshooting

### CORS Errors
**Symptom**: "Access-Control-Allow-Origin" error in console
**Solution**: Verify backend is running on port 8000, check `backend/app/config.py` CORS settings

### Type Mismatches
**Symptom**: TypeScript errors on API responses
**Solution**: Compare `frontend/lib/types/` with `backend/app/schemas/`, update frontend types to match

### Environment Variables Not Loading
**Symptom**: API calls go to wrong URL
**Solution**: Restart Next.js dev server, verify `.env.local` exists and has `NEXT_PUBLIC_` prefix

### Polling Never Completes
**Symptom**: useEstimate progress stuck
**Solution**: Check backend logs, verify estimate processing is working, check max poll timeout (60s)

## Credits

**Backend**: FastAPI + Pydantic schemas
**Frontend**: Next.js 15 + React 19 + TypeScript
**Integration**: Type-safe API client with React hooks pattern
