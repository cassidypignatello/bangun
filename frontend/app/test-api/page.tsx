"use client";

/**
 * API Integration Test Page
 * Simple UI to test all API endpoints
 */

import { useState } from "react";
import { useWorkerSearch, useEstimate } from "@/lib/hooks";

export default function TestApiPage() {
  const { data: workers, loading: searchLoading, error: searchError, search } = useWorkerSearch();
  const { estimate, loading: estimateLoading, error: estimateError, createEstimate } = useEstimate();
  const [testResults, setTestResults] = useState<string[]>([]);

  const addResult = (message: string) => {
    setTestResults(prev => [...prev, `${new Date().toLocaleTimeString()}: ${message}`]);
  };

  const testWorkerSearch = async () => {
    addResult("Testing worker search...");
    await search({
      project_type: "pool_construction",
      location: "Canggu",
      min_trust_score: 40,
      max_results: 3,
    });
  };

  const testEstimate = async () => {
    addResult("Testing cost estimate...");
    await createEstimate({
      project_type: "bathroom_renovation",
      description: "Small bathroom renovation with new tiles, 10 square meters in Canggu",
      location: "Canggu",
      images: [],
    });
  };

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">API Integration Test</h1>

        <div className="space-y-6">
          {/* Worker Search Test */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Worker Search API</h2>
            <button
              onClick={testWorkerSearch}
              disabled={searchLoading}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
            >
              {searchLoading ? "Searching..." : "Test Worker Search"}
            </button>

            {searchError && (
              <div className="mt-4 p-3 bg-red-50 text-red-700 rounded">
                Error: {searchError}
              </div>
            )}

            {workers && (
              <div className="mt-4 p-3 bg-green-50 rounded">
                <p className="font-semibold text-green-800">
                  Found {workers.total_found} workers (showing {workers.showing})
                </p>
                <pre className="mt-2 text-sm overflow-auto">
                  {JSON.stringify(workers, null, 2)}
                </pre>
              </div>
            )}
          </div>

          {/* Estimate Test */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Cost Estimate API</h2>
            <button
              onClick={testEstimate}
              disabled={estimateLoading}
              className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-400"
            >
              {estimateLoading ? "Estimating..." : "Test Cost Estimate"}
            </button>

            {estimateError && (
              <div className="mt-4 p-3 bg-red-50 text-red-700 rounded">
                Error: {estimateError}
              </div>
            )}

            {estimate && (
              <div className="mt-4 p-3 bg-green-50 rounded">
                <p className="font-semibold text-green-800">
                  Estimate: {estimate.estimate_id} - {estimate.status}
                </p>
                <pre className="mt-2 text-sm overflow-auto">
                  {JSON.stringify(estimate, null, 2)}
                </pre>
              </div>
            )}
          </div>

          {/* Test Results Log */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Test Results Log</h2>
            <div className="bg-gray-900 text-green-400 p-4 rounded font-mono text-sm h-64 overflow-auto">
              {testResults.map((result, i) => (
                <div key={i}>{result}</div>
              ))}
              {testResults.length === 0 && (
                <div className="text-gray-500">No tests run yet...</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
