'use client';

import { QuickPriceSearch } from '@/components/QuickPriceSearch';
// CostEstimateForm temporarily hidden - focusing on BoQ upload feature
// import { CostEstimateForm } from '@/components/CostEstimateForm';

export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-blue-50 to-white">
      <div className="max-w-4xl mx-auto px-4 py-12">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            Bangun
          </h1>
          <p className="text-xl text-gray-600">
            Build smarter.
          </p>
        </div>

        {/* Main Feature Cards */}
        <div className="space-y-8">
          {/* BoQ Upload - Coming Soon */}
          <div className="bg-white rounded-lg shadow-lg p-8 border-2 border-dashed border-blue-300">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-3xl">📄</span>
              <div>
                <h2 className="text-2xl font-semibold text-gray-900">
                  Upload Your BoQ
                </h2>
                <span className="inline-block px-2 py-1 text-xs font-medium bg-blue-100 text-blue-700 rounded-full">
                  Coming Soon
                </span>
              </div>
            </div>
            <p className="text-gray-600 mb-6">
              Got a contractor quote? Upload your Bill of Quantity (PDF or Excel) and we&apos;ll
              verify their pricing against real-time market rates from Tokopedia.
            </p>
            <div className="bg-blue-50 rounded-lg p-6 text-center">
              <div className="text-6xl mb-4">📤</div>
              <p className="text-gray-500">
                Drag and drop your BoQ here<br />
                <span className="text-sm">Supports PDF and Excel (.xlsx, .xls)</span>
              </p>
              <button
                disabled
                className="mt-4 px-6 py-3 bg-gray-300 text-gray-500 rounded-lg font-semibold cursor-not-allowed"
              >
                Upload Coming Soon
              </button>
            </div>
            <div className="mt-6 grid grid-cols-3 gap-4 text-center text-sm">
              <div className="bg-green-50 rounded-lg p-3">
                <div className="text-2xl mb-1">💰</div>
                <div className="text-gray-700 font-medium">Verify Pricing</div>
                <div className="text-gray-500 text-xs">Compare against market</div>
              </div>
              <div className="bg-yellow-50 rounded-lg p-3">
                <div className="text-2xl mb-1">🏠</div>
                <div className="text-gray-700 font-medium">Shopping List</div>
                <div className="text-gray-500 text-xs">Items you need to buy</div>
              </div>
              <div className="bg-blue-50 rounded-lg p-3">
                <div className="text-2xl mb-1">📊</div>
                <div className="text-gray-700 font-medium">Confidence Score</div>
                <div className="text-gray-500 text-xs">Know the match quality</div>
              </div>
            </div>
          </div>

          {/* Quick Price Check */}
          <div className="bg-white rounded-lg shadow-lg p-8">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-3xl">🔍</span>
              <h2 className="text-2xl font-semibold text-gray-900">
                Quick Price Check
              </h2>
            </div>
            <p className="text-gray-600 mb-6">
              Need to price a single material or a quick list? Get real-time prices from
              Tokopedia instantly.
            </p>
            <QuickPriceSearch />
          </div>

          {/* Full Project Estimate - Hidden but noted */}
          {/*
          <div className="bg-white rounded-lg shadow-lg p-8">
            <h2 className="text-2xl font-semibold mb-6 text-gray-900">
              Get Your Project Estimate
            </h2>
            <CostEstimateForm />
          </div>
          */}
        </div>

        {/* Footer info */}
        <div className="mt-12 text-center text-gray-500 text-sm">
          <p>
            Prices sourced from Tokopedia marketplace • Updated in real-time •
            <span className="text-green-600"> Bali sellers prioritized</span>
          </p>
        </div>
      </div>
    </main>
  );
}
