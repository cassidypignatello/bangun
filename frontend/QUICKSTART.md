# Quick Start Guide - Frontend API Integration

## 🚀 Get Started in 3 Steps

### 1️⃣ Setup Environment

```bash
cd frontend
cp .env.local.example .env.local
npm install
```

### 2️⃣ Start Development

**Terminal 1 - Backend:**
```bash
cd backend
uvicorn app.main:app --reload
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

### 3️⃣ Test Integration

Open: `http://localhost:3000/test-api`

Click the test buttons to verify API connectivity!

---

## 📚 Common Patterns

### Pattern 1: Search Workers

```typescript
import { useWorkerSearch } from "@/lib/hooks";

function WorkerSearchPage() {
  const { data, loading, error, search } = useWorkerSearch();

  const handleSearch = async () => {
    await search({
      project_type: "pool_construction",
      location: "Canggu",
      min_trust_score: 60,
      max_results: 5,
    });
  };

  if (loading) return <div>Searching...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      <button onClick={handleSearch}>Search</button>
      {data?.workers.map(worker => (
        <WorkerCard key={worker.id} worker={worker} />
      ))}
    </div>
  );
}
```

### Pattern 2: Create Cost Estimate

```typescript
import { useEstimate } from "@/lib/hooks";

function EstimateForm() {
  const { estimate, loading, progress, createEstimate } = useEstimate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    await createEstimate({
      project_type: "bathroom_renovation",
      area_sqm: 10,
      location: "Canggu",
    });
  };

  return (
    <form onSubmit={handleSubmit}>
      {/* form fields */}
      <button type="submit" disabled={loading}>
        {loading ? `Processing... ${progress}%` : "Get Estimate"}
      </button>

      {estimate && (
        <div>
          Materials Total: Rp {estimate.total_cost_idr.toLocaleString()}
        </div>
      )}
    </form>
  );
}
```

### Pattern 3: Unlock Worker Details

```typescript
import { usePayment, PaymentMethod } from "@/lib/hooks";

function UnlockButton({ workerId }: { workerId: string }) {
  const { loading, initiateUnlock } = usePayment();

  const handleUnlock = async () => {
    await initiateUnlock(workerId, PaymentMethod.GOPAY);
    // Automatically redirects to payment page
  };

  return (
    <button onClick={handleUnlock} disabled={loading}>
      {loading ? "Processing..." : "Unlock Details - Rp 50,000"}
    </button>
  );
}
```

---

## 🎯 Import Cheat Sheet

```typescript
// Hooks (recommended for components)
import {
  useWorkerSearch,
  useWorkerDetails,
  useEstimate,
  usePayment
} from "@/lib/hooks";

// Direct API (for server actions or advanced use)
import {
  workersApi,
  paymentsApi,
  estimatesApi,
  materialsApi
} from "@/lib/api";

// Types
import type {
  WorkerPreview,
  WorkerFullDetails,
  WorkerSearchRequest,
  EstimateResponse,
  PaymentMethod,
  TrustLevel
} from "@/lib/types";
```

---

## 🔧 Troubleshooting

### ❌ CORS Error
```
Access to fetch at 'http://localhost:8000' has been blocked by CORS policy
```

**Fix**: Ensure backend is running and CORS is configured:
```bash
# Check backend is running on port 8000
curl http://localhost:8000/health

# Verify CORS settings in backend/app/config.py
```

### ❌ Types Don't Match
```
Type 'WorkerPreview' is not assignable to type...
```

**Fix**: Backend schemas may have changed. Compare:
- `frontend/lib/types/worker.ts`
- `backend/app/schemas/worker.py`

### ❌ Environment Variable Not Found
```
NEXT_PUBLIC_API_URL is not defined
```

**Fix**:
1. Copy `.env.local.example` to `.env.local`
2. Restart Next.js dev server (`npm run dev`)

---

## 📖 Full Documentation

- **Detailed Guide**: `frontend/lib/README.md`
- **Integration Summary**: `frontend/INTEGRATION.md`
- **Test Page**: `http://localhost:3000/test-api`

---

## ✅ Verification Checklist

Before building features, verify:

- [ ] Backend running on `http://localhost:8000`
- [ ] Frontend running on `http://localhost:3000`
- [ ] `.env.local` file exists with `NEXT_PUBLIC_API_URL`
- [ ] Test page (`/test-api`) shows successful API calls
- [ ] No CORS errors in browser console
- [ ] TypeScript compiler shows no errors (`npm run build`)

---

## 🎨 Next Steps

Now that API integration is complete, you can:

1. **Build UI Components** - Use the hooks in your pages
2. **Add Forms** - Material estimate form, worker search filters
3. **Style Components** - Tailwind CSS is already configured
4. **Add Validation** - Form validation with Zod or React Hook Form
5. **Implement Routing** - Worker detail pages, estimate results

**Recommended Starting Point**: Worker search interface on homepage

```typescript
// app/page.tsx
import { useWorkerSearch } from "@/lib/hooks";

export default function HomePage() {
  const { data, search } = useWorkerSearch();

  // Build your search UI here!
  return <div>Worker Search Interface</div>;
}
```
