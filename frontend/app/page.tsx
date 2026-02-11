'use client';

import { BoQUpload } from '@/components/BoQUpload';
import { QuickPriceSearch } from '@/components/QuickPriceSearch';

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
          {/* BoQ Upload */}
          <div className="bg-white rounded-lg shadow-lg p-8">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-3xl">📄</span>
              <h2 className="text-2xl font-semibold text-gray-900">
                Upload Your BoQ
              </h2>
            </div>
            <p className="text-gray-600 mb-6">
              Got a contractor quote? Upload your Bill of Quantity (PDF or Excel) and we&apos;ll
              verify their pricing against real-time market rates.
            </p>
            <BoQUpload />
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
