'use client';

import { useState } from 'react';
import { useEstimate } from '@/lib/hooks';
import type { CreateEstimateRequest } from '@/lib/api/estimates';

interface CostEstimateFormProps {
  onEstimateComplete?: () => void;
}

export function CostEstimateForm({ onEstimateComplete }: CostEstimateFormProps) {
  const { estimate, loading, error, progress, createEstimate } = useEstimate();
  const [formData, setFormData] = useState<CreateEstimateRequest>({
    project_type: '',
    area_sqm: undefined,
    location: '',
    specifications: {},
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await createEstimate(formData);
    onEstimateComplete?.();
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;

    if (name === 'area_sqm') {
      setFormData((prev) => ({
        ...prev,
        [name]: value === '' ? undefined : parseFloat(value),
      }));
    } else {
      setFormData((prev) => ({
        ...prev,
        [name]: value,
      }));
    }
  };

  const formatPrice = (priceIdr: number) => {
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      minimumFractionDigits: 0,
    }).format(priceIdr);
  };

  return (
    <div className="space-y-6">
      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label htmlFor="project_type" className="block text-sm font-medium text-gray-700 mb-2">
            Project Type
          </label>
          <input
            type="text"
            id="project_type"
            name="project_type"
            value={formData.project_type}
            onChange={handleChange}
            placeholder="e.g., Villa Renovation, Bathroom Remodel"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            required
          />
        </div>

        <div>
          <label htmlFor="area_sqm" className="block text-sm font-medium text-gray-700 mb-2">
            Area (square meters) - optional
          </label>
          <input
            type="number"
            id="area_sqm"
            name="area_sqm"
            value={formData.area_sqm || ''}
            onChange={handleChange}
            min="1"
            step="0.1"
            placeholder="e.g., 100"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        <div>
          <label htmlFor="location" className="block text-sm font-medium text-gray-700 mb-2">
            Location (optional)
          </label>
          <input
            type="text"
            id="location"
            name="location"
            value={formData.location}
            onChange={handleChange}
            placeholder="e.g., Canggu, Ubud"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
            {error}
          </div>
        )}

        {loading && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-blue-800 font-medium">Processing estimate...</span>
              <span className="text-blue-600">{progress}%</span>
            </div>
            <div className="w-full bg-blue-200 rounded-full h-2">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 text-white py-3 px-6 rounded-lg font-semibold hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? 'Generating Estimate...' : 'Get Cost Estimate'}
        </button>
      </form>

      {estimate && estimate.status === 'completed' && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-6">
          <div className="border-b border-gray-200 pb-4">
            <h3 className="text-xl font-semibold text-gray-900 mb-2">
              Estimate for {estimate.project_type}
            </h3>
            <p className="text-sm text-gray-500">
              Created {new Date(estimate.created_at).toLocaleDateString()}
            </p>
          </div>

          <div className="space-y-4">
            <h4 className="font-semibold text-gray-900">Bill of Materials</h4>
            {estimate.bom_items.map((item, idx) => (
              <div key={idx} className="flex justify-between items-start p-3 bg-gray-50 rounded-lg">
                <div className="flex-1">
                  <p className="font-medium text-gray-900">{item.material_name}</p>
                  <p className="text-sm text-gray-600">
                    {item.quantity} {item.unit} @ {formatPrice(item.unit_price_idr)}/{item.unit}
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-gray-500">Source: {item.source}</span>
                    <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded">
                      {Math.round(item.confidence * 100)}% confidence
                    </span>
                  </div>
                  {item.marketplace_url && (
                    <a
                      href={item.marketplace_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-600 hover:underline mt-1 inline-block"
                    >
                      View on marketplace →
                    </a>
                  )}
                </div>
                <div className="text-right">
                  <p className="font-semibold text-gray-900">
                    {formatPrice(item.total_price_idr)}
                  </p>
                </div>
              </div>
            ))}
          </div>

          <div className="border-t border-gray-200 pt-4 space-y-2">
            <div className="flex justify-between text-gray-700">
              <span>Materials Total:</span>
              <span className="font-semibold">{formatPrice(estimate.total_cost_idr)}</span>
            </div>
            <div className="flex justify-between text-gray-700">
              <span>Estimated Labor:</span>
              <span className="font-semibold">{formatPrice(estimate.labor_cost_idr)}</span>
            </div>
            <div className="flex justify-between text-lg font-bold text-gray-900 pt-2 border-t border-gray-200">
              <span>Grand Total:</span>
              <span>{formatPrice(estimate.grand_total_idr)}</span>
            </div>
          </div>

          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <p className="text-sm text-yellow-800">
              💡 <strong>Note:</strong> This estimate is based on current market prices in Bali.
              Actual costs may vary. Labor costs are approximate and should be confirmed with workers.
            </p>
          </div>
        </div>
      )}

      {estimate && estimate.status === 'failed' && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">
            ❌ Failed to generate estimate: {estimate.error_message || 'Unknown error'}
          </p>
        </div>
      )}
    </div>
  );
}
