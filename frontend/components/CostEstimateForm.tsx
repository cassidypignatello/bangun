'use client';

import { useState } from 'react';
import { useEstimate } from '@/lib/hooks';
import type { CreateEstimateRequest } from '@/lib/api/estimates';
import { MaterialChecklist } from './MaterialChecklist';

interface CostEstimateFormProps {
  onEstimateComplete?: () => void;
}

export function CostEstimateForm({ onEstimateComplete }: CostEstimateFormProps) {
  const { estimate, loading, error, progress, progressMessage, createEstimate } = useEstimate();
  const [formData, setFormData] = useState<CreateEstimateRequest>({
    description: '',
    images: [],
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation(); // Prevent event bubbling

    try {
      await createEstimate(formData);
      onEstimateComplete?.();
    } catch (error) {
      // Error handling is done in the hook
      console.error('Form submission error:', error);
    }
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
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
          <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-2">
            Describe Your Project
          </label>
          <textarea
            id="description"
            name="description"
            value={formData.description}
            onChange={handleChange}
            placeholder="Tell us about your renovation or construction project. Include details like dimensions, materials you prefer, and any specific requirements...

Example: I want to renovate my 3x4m bathroom with a walk-in shower, new ceramic tiles, modern fixtures, and waterproofing."
            rows={6}
            minLength={10}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-black"
            required
          />
          <p className="mt-1 text-sm text-gray-500">
            The more detail you provide, the more accurate your estimate will be.
          </p>
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
            <div className="w-full bg-blue-200 rounded-full h-2.5 mb-2">
              <div
                className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
            {progressMessage && (
              <p className="text-sm text-blue-700 truncate">{progressMessage}</p>
            )}
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
          {/* Header */}
          <div className="border-b border-gray-200 pb-4">
            <h3 className="text-xl font-semibold text-gray-900 mb-2">
              Your Project Estimate
            </h3>
            <p className="text-sm text-gray-500">
              Created {new Date(estimate.created_at).toLocaleDateString()}
            </p>
          </div>

          {/* Interactive Shopping List */}
          <MaterialChecklist bomItems={estimate.bom_items} />

          {/* Labor & Grand Total Summary */}
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-2">
            <div className="flex justify-between text-gray-700">
              <span>Estimated Labor (30% of materials):</span>
              <span className="font-semibold">{formatPrice(estimate.labor_cost_idr)}</span>
            </div>
            <div className="flex justify-between text-lg font-bold text-gray-900 pt-2 border-t border-gray-300">
              <span>Project Grand Total:</span>
              <span>{formatPrice(estimate.grand_total_idr)}</span>
            </div>
          </div>

          {/* Note */}
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
