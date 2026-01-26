'use client';

import { useState } from 'react';
import { materialsApi, type PriceLookupResponse, type PriceLookupRequest } from '@/lib/api/materials';

interface QuickPriceSearchProps {
  onSearchComplete?: () => void;
}

export function QuickPriceSearch({ onSearchComplete }: QuickPriceSearchProps) {
  const [searchMode, setSearchMode] = useState<'single' | 'multiple'>('single');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<PriceLookupResponse[] | null>(null);
  const [stats, setStats] = useState<{ cacheHits: number; scrapeCount: number; totalCost: number } | null>(null);

  // Single search state
  const [materialName, setMaterialName] = useState('');
  const [quantity, setQuantity] = useState<number>(1);
  const [unit, setUnit] = useState('pcs');

  // Multiple search state (newline-separated list)
  const [materialsList, setMaterialsList] = useState('');

  const formatPrice = (priceIdr: number) => {
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      minimumFractionDigits: 0,
    }).format(priceIdr);
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return 'text-green-600';
    if (confidence >= 0.6) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getSourceBadge = (source: string) => {
    switch (source) {
      case 'cached':
      case 'historical':
      case 'historical_fuzzy':
        return <span className="px-2 py-0.5 text-xs bg-green-100 text-green-700 rounded-full">⚡ Cached</span>;
      case 'tokopedia':
        return <span className="px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded-full">🛒 Live</span>;
      case 'estimated':
        return <span className="px-2 py-0.5 text-xs bg-yellow-100 text-yellow-700 rounded-full">📊 Estimated</span>;
      default:
        return <span className="px-2 py-0.5 text-xs bg-gray-100 text-gray-700 rounded-full">{source}</span>;
    }
  };

  const handleSingleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!materialName.trim()) return;

    setLoading(true);
    setError(null);
    setResults(null);
    setStats(null);

    try {
      const response = await materialsApi.getPrice(materialName.trim(), quantity, unit);
      if (response.data) {
        setResults([response.data]);
        setStats({
          cacheHits: response.data.source === 'cached' || response.data.source.includes('historical') ? 1 : 0,
          scrapeCount: response.data.source === 'tokopedia' ? 1 : 0,
          totalCost: response.data.total_price_idr,
        });
      }
      onSearchComplete?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to get price');
    } finally {
      setLoading(false);
    }
  };

  const handleMultipleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const lines = materialsList.trim().split('\n').filter(line => line.trim());
    if (lines.length === 0) return;

    setLoading(true);
    setError(null);
    setResults(null);
    setStats(null);

    // Parse each line: "material name" or "material name, qty, unit"
    const materials: PriceLookupRequest[] = lines.map(line => {
      const parts = line.split(',').map(p => p.trim());
      return {
        material_name: parts[0],
        quantity: parts[1] ? parseFloat(parts[1]) : 1,
        unit: parts[2] || 'pcs',
      };
    });

    try {
      const response = await materialsApi.getPricesBatch(materials);
      if (response.data) {
        setResults(response.data.prices);
        setStats({
          cacheHits: response.data.cache_hits,
          scrapeCount: response.data.scrape_count,
          totalCost: response.data.total_cost_idr,
        });
      }
      onSearchComplete?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to get prices');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Mode Toggle */}
      <div className="flex border-b border-gray-200">
        <button
          type="button"
          onClick={() => setSearchMode('single')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            searchMode === 'single'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Single Item
        </button>
        <button
          type="button"
          onClick={() => setSearchMode('multiple')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            searchMode === 'multiple'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Multiple Items
        </button>
      </div>

      {/* Single Item Search */}
      {searchMode === 'single' && (
        <form onSubmit={handleSingleSearch} className="space-y-4">
          <div>
            <label htmlFor="materialName" className="block text-sm font-medium text-gray-700 mb-1">
              What do you need priced?
            </label>
            <input
              id="materialName"
              type="text"
              value={materialName}
              onChange={(e) => setMaterialName(e.target.value)}
              placeholder="e.g., gypsum board 9mm, tempered glass 8mm, semen 50kg"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-black"
              required
            />
          </div>

          <div className="flex gap-4">
            <div className="flex-1">
              <label htmlFor="quantity" className="block text-sm font-medium text-gray-700 mb-1">
                Quantity
              </label>
              <input
                id="quantity"
                type="number"
                min="0.1"
                step="0.1"
                value={quantity}
                onChange={(e) => setQuantity(parseFloat(e.target.value) || 1)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-black"
              />
            </div>
            <div className="flex-1">
              <label htmlFor="unit" className="block text-sm font-medium text-gray-700 mb-1">
                Unit
              </label>
              <select
                id="unit"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-black"
              >
                <option value="pcs">pcs (pieces)</option>
                <option value="m2">m² (square meters)</option>
                <option value="m">m (meters)</option>
                <option value="kg">kg (kilograms)</option>
                <option value="liter">liter</option>
                <option value="sak">sak (bags)</option>
                <option value="roll">roll</option>
                <option value="lembar">lembar (sheets)</option>
              </select>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading || !materialName.trim()}
            className="w-full bg-green-600 text-white py-3 px-6 rounded-lg font-semibold hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Getting Price...' : '🔍 Get Price'}
          </button>
        </form>
      )}

      {/* Multiple Items Search */}
      {searchMode === 'multiple' && (
        <form onSubmit={handleMultipleSearch} className="space-y-4">
          <div>
            <label htmlFor="materialsList" className="block text-sm font-medium text-gray-700 mb-1">
              Enter materials (one per line)
            </label>
            <textarea
              id="materialsList"
              value={materialsList}
              onChange={(e) => setMaterialsList(e.target.value)}
              placeholder={`gypsum board 9mm, 10, m2
tempered glass 8mm, 5, m2
semen 50kg, 20, pcs
keramik 60x60, 15, m2

Format: material name, quantity, unit
(quantity and unit are optional)`}
              rows={6}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-black font-mono text-sm"
              required
            />
            <p className="mt-1 text-xs text-gray-500">
              Format: material name, quantity, unit (quantity and unit are optional, defaults to 1 pcs)
            </p>
          </div>

          <button
            type="submit"
            disabled={loading || !materialsList.trim()}
            className="w-full bg-green-600 text-white py-3 px-6 rounded-lg font-semibold hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Getting Prices...' : '🔍 Get All Prices'}
          </button>
        </form>
      )}

      {/* Loading State */}
      {loading && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-center">
          <div className="animate-spin inline-block w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full mb-2"></div>
          <p className="text-blue-800">Checking prices... This may take a moment if we need to fetch live data.</p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Results */}
      {results && results.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          {/* Stats Header */}
          {stats && (
            <div className="bg-gray-50 border-b border-gray-200 px-4 py-3 flex flex-wrap gap-4 text-sm">
              <span className="text-gray-600">
                <strong>{results.length}</strong> item{results.length !== 1 ? 's' : ''} priced
              </span>
              {stats.cacheHits > 0 && (
                <span className="text-green-600">
                  ⚡ {stats.cacheHits} from cache
                </span>
              )}
              {stats.scrapeCount > 0 && (
                <span className="text-blue-600">
                  🛒 {stats.scrapeCount} live lookup{stats.scrapeCount !== 1 ? 's' : ''}
                </span>
              )}
              {results.length > 1 && (
                <span className="ml-auto font-semibold text-gray-900">
                  Total: {formatPrice(stats.totalCost)}
                </span>
              )}
            </div>
          )}

          {/* Results List */}
          <div className="divide-y divide-gray-100">
            {results.map((result, index) => (
              <div key={index} className="p-4 hover:bg-gray-50">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-gray-900">{result.material_name}</span>
                      {getSourceBadge(result.source)}
                    </div>
                    <div className="text-sm text-gray-500 mt-1">
                      {result.quantity} {result.unit} × {formatPrice(result.unit_price_idr)}/{result.unit}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-semibold text-gray-900">
                      {formatPrice(result.total_price_idr)}
                    </div>
                    <div className={`text-xs ${getConfidenceColor(result.confidence)}`}>
                      {Math.round(result.confidence * 100)}% confidence
                    </div>
                  </div>
                </div>

                {/* Marketplace Link */}
                {result.affiliate_url && (
                  <div className="mt-2">
                    <a
                      href={result.affiliate_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-blue-600 hover:text-blue-800 hover:underline"
                    >
                      🛒 View on Tokopedia →
                    </a>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
