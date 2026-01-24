'use client';

// Worker search components temporarily hidden - focusing on BOM generation
// import { WorkerSearchForm } from '@/components/WorkerSearchForm';
// import { WorkerSearchResults } from '@/components/WorkerSearchResults';
import { CostEstimateForm } from '@/components/CostEstimateForm';
// import { useWorkerSearch } from '@/lib/hooks';

export default function Home() {
  // const { data } = useWorkerSearch();

  return (
    <main className="min-h-screen bg-gradient-to-b from-blue-50 to-white">
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            Bali Renovation OS
          </h1>
          <p className="text-xl text-gray-600">
            Fair pricing and trusted workers for your Bali renovation
          </p>
        </div>

        {/* Worker search section temporarily hidden - focusing on BOM generation */}
        {/* <WorkerSearchForm /> */}

        {/* {data && (
          <WorkerSearchResults
            workers={data.workers}
            unlockPriceIdr={data.unlock_price_idr}
          />
        )} */}

        <div className="bg-white rounded-lg shadow-lg p-8">
          <h2 className="text-2xl font-semibold mb-6 text-gray-900">
            Get Your Project Estimate
          </h2>
          <p className="text-gray-600 mb-6">
            Tell us about your renovation project and we&apos;ll provide accurate material costs
            and labor estimates based on current Bali market prices.
          </p>
          <CostEstimateForm />
        </div>
      </div>
    </main>
  );
}
