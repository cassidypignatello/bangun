'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  boqApi,
  type BoQUploadResponse,
  type BoQJobStatusResponse,
  type BoQAnalysisResults,
  type BoQItemPriced,
} from '@/lib/api/boq';

type UploadState = 'idle' | 'uploading' | 'processing' | 'completed' | 'failed';

export function BoQUpload() {
  const [state, setState] = useState<UploadState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState<string>('');
  const [results, setResults] = useState<BoQAnalysisResults | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(price);
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.85) return 'text-green-600 bg-green-50';
    if (confidence >= 0.60) return 'text-yellow-600 bg-yellow-50';
    return 'text-gray-600 bg-gray-50';
  };

  const getConfidenceLabel = (confidence: number) => {
    if (confidence >= 0.85) return 'High';
    if (confidence >= 0.60) return 'Medium';
    return 'Low';
  };

  const handleFileSelect = useCallback((file: File) => {
    // Validate file type
    const validTypes = [
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-excel',
    ];
    const validExtensions = ['.pdf', '.xlsx', '.xls'];

    const hasValidType = validTypes.includes(file.type);
    const hasValidExtension = validExtensions.some(ext =>
      file.name.toLowerCase().endsWith(ext)
    );

    if (!hasValidType && !hasValidExtension) {
      setError('Please upload a PDF or Excel file (.pdf, .xlsx, .xls)');
      return;
    }

    // Validate file size (10MB max)
    if (file.size > 10 * 1024 * 1024) {
      setError('File too large. Maximum size is 10MB.');
      return;
    }

    setSelectedFile(file);
    setError(null);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file) {
        handleFileSelect(file);
      }
    },
    [handleFileSelect]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const pollStatus = useCallback(async (jobId: string) => {
    const response = await boqApi.getStatus(jobId);

    if (response.error) {
      setError(response.error.message);
      setState('failed');
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
      return;
    }

    const status = response.data!;
    setProgress(status.progress_percent);
    setStatusMessage(status.message || '');

    if (status.status === 'completed') {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }

      // Fetch full results
      const resultsResponse = await boqApi.getResults(jobId);
      if (resultsResponse.error) {
        setError(resultsResponse.error.message);
        setState('failed');
      } else {
        setResults(resultsResponse.data!);
        setState('completed');
      }
    } else if (status.status === 'failed') {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
      setError(status.error_message || 'Processing failed');
      setState('failed');
    }
  }, []);

  const handleUpload = async () => {
    if (!selectedFile) return;

    setState('uploading');
    setError(null);
    setProgress(0);

    const response = await boqApi.uploadFile(selectedFile);

    if (response.error) {
      setError(response.error.message);
      setState('failed');
      return;
    }

    const data = response.data!;
    setJobId(data.job_id);
    setState('processing');
    setStatusMessage(data.message);

    // Start polling for status
    pollIntervalRef.current = setInterval(() => {
      pollStatus(data.job_id);
    }, 2000);

    // Initial poll
    pollStatus(data.job_id);
  };

  const handleReset = () => {
    setState('idle');
    setSelectedFile(null);
    setJobId(null);
    setProgress(0);
    setStatusMessage('');
    setResults(null);
    setError(null);
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
    }
  };

  // Render different states
  if (state === 'completed' && results) {
    return (
      <div className="space-y-6">
        {/* Summary Header */}
        <div className="bg-gradient-to-r from-green-50 to-blue-50 rounded-lg p-6 border border-green-200">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-xl font-semibold text-gray-900">
                Analysis Complete
              </h3>
              <p className="text-gray-600">
                {results.metadata.filename}
                {results.metadata.contractor_name && (
                  <span className="ml-2 text-sm">• {results.metadata.contractor_name}</span>
                )}
              </p>
            </div>
            <button
              onClick={handleReset}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 border rounded-lg"
            >
              Upload Another
            </button>
          </div>

          {/* Key Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-lg p-4 shadow-sm">
              <div className="text-sm text-gray-500">Contractor Quote</div>
              <div className="text-lg font-semibold text-gray-900">
                {formatPrice(results.summary.contractor_total)}
              </div>
            </div>
            <div className="bg-white rounded-lg p-4 shadow-sm">
              <div className="text-sm text-gray-500">Market Estimate</div>
              <div className="text-lg font-semibold text-blue-600">
                {formatPrice(results.summary.market_estimate)}
              </div>
            </div>
            <div className="bg-white rounded-lg p-4 shadow-sm">
              <div className="text-sm text-gray-500">Potential Savings</div>
              <div className="text-lg font-semibold text-green-600">
                {formatPrice(results.summary.potential_savings)}
                <span className="text-sm font-normal ml-1">
                  ({results.summary.savings_percent.toFixed(1)}%)
                </span>
              </div>
            </div>
            <div className="bg-white rounded-lg p-4 shadow-sm">
              <div className="text-sm text-gray-500">Items Analyzed</div>
              <div className="text-lg font-semibold text-gray-900">
                {results.summary.priced_count}/{results.summary.materials_count}
                <span className="text-sm font-normal ml-1">priced</span>
              </div>
            </div>
          </div>
        </div>

        {/* Owner Supply Items - Shopping List */}
        {results.owner_supply_items.length > 0 && (
          <div className="bg-white rounded-lg shadow-lg p-6 border-l-4 border-yellow-400">
            <h4 className="text-lg font-semibold text-gray-900 mb-1 flex items-center gap-2">
              <span>🛒</span> Your Shopping List
              <span className="text-sm font-normal text-gray-500">
                ({results.owner_supply_items.length} items to buy)
              </span>
            </h4>
            <p className="text-sm text-gray-600 mb-4">
              These items are marked &quot;Supply By Owner&quot; - you need to purchase them yourself
            </p>
            <div className="space-y-3">
              {results.owner_supply_items.map((item, idx) => (
                <ItemCard key={item.id || idx} item={item} showPricing />
              ))}
            </div>
          </div>
        )}

        {/* Overpriced Items */}
        {results.overpriced_items.length > 0 && (
          <div className="bg-white rounded-lg shadow-lg p-6 border-l-4 border-red-400">
            <h4 className="text-lg font-semibold text-gray-900 mb-1 flex items-center gap-2">
              <span>⚠️</span> Potentially Overpriced
              <span className="text-sm font-normal text-gray-500">
                ({results.overpriced_items.length} items &gt;10% above market)
              </span>
            </h4>
            <p className="text-sm text-gray-600 mb-4">
              These items may be priced higher than market rates
            </p>
            <div className="space-y-3">
              {results.overpriced_items.slice(0, 10).map((item, idx) => (
                <ItemCard key={item.id || idx} item={item} showPricing showDifference />
              ))}
            </div>
          </div>
        )}

        {/* All Materials Summary */}
        <div className="bg-white rounded-lg shadow-lg p-6">
          <h4 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <span>📋</span> All Materials
            <span className="text-sm font-normal text-gray-500">
              ({results.all_materials.length} items)
            </span>
          </h4>
          <div className="max-h-96 overflow-y-auto space-y-2">
            {results.all_materials.map((item, idx) => (
              <ItemCard key={item.id || idx} item={item} compact />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Drop Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onClick={() => state === 'idle' && fileInputRef.current?.click()}
        className={`
          relative rounded-lg border-2 border-dashed p-8 text-center transition-all
          ${state === 'idle' ? 'cursor-pointer hover:border-blue-400 hover:bg-blue-50/50' : ''}
          ${selectedFile && state === 'idle' ? 'border-blue-400 bg-blue-50' : 'border-gray-300'}
          ${state === 'uploading' || state === 'processing' ? 'border-blue-400 bg-blue-50' : ''}
          ${state === 'failed' ? 'border-red-300 bg-red-50' : ''}
        `}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.xlsx,.xls"
          onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
          className="hidden"
        />

        {state === 'idle' && !selectedFile && (
          <>
            <div className="text-5xl mb-4">📄</div>
            <p className="text-gray-700 font-medium">
              Drop your BoQ file here
            </p>
            <p className="text-gray-500 text-sm mt-1">
              or click to browse • PDF, Excel (.xlsx, .xls)
            </p>
          </>
        )}

        {state === 'idle' && selectedFile && (
          <>
            <div className="text-5xl mb-4">✅</div>
            <p className="text-gray-900 font-medium">{selectedFile.name}</p>
            <p className="text-gray-500 text-sm mt-1">
              {(selectedFile.size / 1024).toFixed(1)} KB • Ready to analyze
            </p>
          </>
        )}

        {(state === 'uploading' || state === 'processing') && (
          <>
            <div className="text-5xl mb-4 animate-pulse">⏳</div>
            <p className="text-blue-700 font-medium">
              {state === 'uploading' ? 'Uploading...' : statusMessage || 'Processing...'}
            </p>
            {state === 'processing' && (
              <div className="mt-4 w-full max-w-xs mx-auto">
                <div className="bg-blue-100 rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-blue-500 h-full transition-all duration-500"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <p className="text-sm text-gray-500 mt-2">{progress}% complete</p>
              </div>
            )}
          </>
        )}

        {state === 'failed' && (
          <>
            <div className="text-5xl mb-4">❌</div>
            <p className="text-red-700 font-medium">Upload Failed</p>
            <p className="text-red-600 text-sm mt-1">{error}</p>
          </>
        )}
      </div>

      {/* Action Buttons */}
      {state === 'idle' && selectedFile && (
        <button
          onClick={handleUpload}
          className="w-full py-3 px-6 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg transition-colors"
        >
          Analyze BoQ
        </button>
      )}

      {state === 'failed' && (
        <button
          onClick={handleReset}
          className="w-full py-3 px-6 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-lg transition-colors"
        >
          Try Again
        </button>
      )}

      {/* Info */}
      {state === 'idle' && (
        <div className="grid grid-cols-3 gap-4 text-center text-sm">
          <div className="bg-green-50 rounded-lg p-3">
            <div className="text-2xl mb-1">💰</div>
            <div className="text-gray-700 font-medium">Verify Pricing</div>
            <div className="text-gray-500 text-xs">Compare against market</div>
          </div>
          <div className="bg-yellow-50 rounded-lg p-3">
            <div className="text-2xl mb-1">🛒</div>
            <div className="text-gray-700 font-medium">Shopping List</div>
            <div className="text-gray-500 text-xs">Items you need to buy</div>
          </div>
          <div className="bg-blue-50 rounded-lg p-3">
            <div className="text-2xl mb-1">📊</div>
            <div className="text-gray-700 font-medium">Confidence Score</div>
            <div className="text-gray-500 text-xs">Know the match quality</div>
          </div>
        </div>
      )}

      {/* Processing Info */}
      {state === 'processing' && (
        <p className="text-center text-sm text-gray-500">
          Analysis typically takes 1-3 minutes depending on document size
        </p>
      )}
    </div>
  );
}

// Item Card Component
function ItemCard({
  item,
  showPricing = false,
  showDifference = false,
  compact = false,
}: {
  item: BoQItemPriced;
  showPricing?: boolean;
  showDifference?: boolean;
  compact?: boolean;
}) {
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(price);
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.85) return 'text-green-600 bg-green-100';
    if (confidence >= 0.60) return 'text-yellow-600 bg-yellow-100';
    return 'text-gray-600 bg-gray-100';
  };

  if (compact) {
    return (
      <div className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded hover:bg-gray-100">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-900 truncate">{item.description}</p>
          {item.quantity && item.unit && (
            <p className="text-xs text-gray-500">
              {item.quantity} {item.unit}
            </p>
          )}
        </div>
        <div className="text-right ml-4">
          {item.contractor_total ? (
            <p className="text-sm font-medium text-gray-900">
              {formatPrice(item.contractor_total)}
            </p>
          ) : null}
          {item.match_confidence !== undefined && item.match_confidence > 0 && (
            <span className={`text-xs px-1.5 py-0.5 rounded ${getConfidenceColor(item.match_confidence)}`}>
              {Math.round(item.match_confidence * 100)}%
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-50 rounded-lg p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <p className="font-medium text-gray-900">{item.description}</p>
          {item.quantity && item.unit && (
            <p className="text-sm text-gray-500 mt-1">
              {item.quantity} {item.unit}
              {item.contractor_unit_price && (
                <span> @ {formatPrice(item.contractor_unit_price)}</span>
              )}
            </p>
          )}
        </div>
        {item.match_confidence !== undefined && item.match_confidence > 0 && (
          <span className={`text-xs px-2 py-1 rounded-full ${getConfidenceColor(item.match_confidence)}`}>
            {Math.round(item.match_confidence * 100)}% match
          </span>
        )}
      </div>

      {showPricing && item.tokopedia_product_name && (
        <div className="mt-3 pt-3 border-t border-gray-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Market Match:</p>
              <p className="text-sm font-medium text-gray-900">{item.tokopedia_product_name}</p>
              {item.tokopedia_seller_location && (
                <p className="text-xs text-gray-500">📍 {item.tokopedia_seller_location}</p>
              )}
            </div>
            <div className="text-right">
              {item.tokopedia_price && (
                <p className="text-lg font-semibold text-blue-600">
                  {formatPrice(item.tokopedia_price)}
                </p>
              )}
              {item.tokopedia_url && (
                <a
                  href={item.tokopedia_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-500 hover:underline"
                >
                  View on Tokopedia →
                </a>
              )}
            </div>
          </div>
        </div>
      )}

      {showDifference && item.price_difference_percent !== undefined && (
        <div className="mt-3 pt-3 border-t border-gray-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">
                Contractor: {item.contractor_unit_price ? formatPrice(item.contractor_unit_price) : '—'}
              </p>
              <p className="text-sm text-gray-600">
                Market: {item.market_unit_price ? formatPrice(item.market_unit_price) : '—'}
              </p>
            </div>
            <div className="text-right">
              <p className="text-lg font-semibold text-red-600">
                +{item.price_difference_percent?.toFixed(1)}%
              </p>
              <p className="text-sm text-gray-500">above market</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
