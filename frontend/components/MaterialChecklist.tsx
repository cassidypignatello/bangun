'use client';

import { useEffect, useRef } from 'react';
import { useMaterialChecklist, type ShoppingItem } from '@/lib/hooks';
import type { BOMItem } from '@/lib/types';

interface MaterialChecklistProps {
  /** Bill of Materials items from the estimate */
  bomItems: BOMItem[];
  /** Project type for display context */
  projectType?: string;
  /** Optional callback when all items are purchased */
  onComplete?: () => void;
}

/**
 * Interactive shopping list for Bill of Materials.
 *
 * Renders BOM items as a checklist with:
 * - Item details (name, quantity, estimated price)
 * - "Buy on Tokopedia" buttons with affiliate tracking
 * - Shopping progress bar
 * - Summary card with total estimated cost
 *
 * Opens affiliate links in new tabs to preserve user's place.
 */
export function MaterialChecklist({
  bomItems,
  projectType,
  onComplete,
}: MaterialChecklistProps) {
  const {
    items,
    purchasedCount,
    totalCount,
    progressPercent,
    totalEstimatedCost,
    markAsPurchased,
    togglePurchased,
    resetProgress,
    isComplete,
  } = useMaterialChecklist(bomItems);

  // Track previous isComplete state to detect transitions
  const wasCompleteRef = useRef(false);

  // Call onComplete when isComplete transitions from false to true
  useEffect(() => {
    if (isComplete && !wasCompleteRef.current) {
      onComplete?.();
    }
    wasCompleteRef.current = isComplete;
  }, [isComplete, onComplete]);

  const formatPrice = (priceIdr: number) => {
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      minimumFractionDigits: 0,
    }).format(priceIdr);
  };

  const handleBuyClick = (item: ShoppingItem) => {
    // Use affiliate URL if available, fall back to marketplace URL
    const buyUrl = item.affiliate_url || item.marketplace_url;

    if (buyUrl) {
      // Open in new tab to preserve user's place
      window.open(buyUrl, '_blank', 'noopener,noreferrer');
      // Mark as purchased after clicking
      markAsPurchased(item.id);
    }
  };

  if (items.length === 0) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center">
        <p className="text-gray-600">No materials in this estimate.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h3 className="text-xl font-semibold text-gray-900">
            Materials Shopping List
          </h3>
          {projectType && (
            <p className="text-sm text-gray-500 mt-1">
              {projectType.replace(/_/g, ' ')}
            </p>
          )}
        </div>
        {purchasedCount > 0 && (
          <button
            onClick={resetProgress}
            className="text-sm text-gray-500 hover:text-gray-700 underline"
          >
            Reset progress
          </button>
        )}
      </div>

      {/* Shopping Progress Bar */}
      <div className="bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-green-800 font-medium flex items-center gap-2">
            <ShoppingCartIcon />
            Shopping Progress
          </span>
          <span className="text-green-600 font-semibold">
            {purchasedCount} / {totalCount} items ({progressPercent}%)
          </span>
        </div>
        <div className="w-full bg-green-200 rounded-full h-3">
          <div
            className="bg-gradient-to-r from-green-500 to-emerald-500 h-3 rounded-full transition-all duration-500 ease-out"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        {isComplete && (
          <p className="text-green-700 text-sm mt-2 flex items-center gap-1">
            <CheckCircleIcon />
            All materials purchased! Ready for your renovation.
          </p>
        )}
      </div>

      {/* Materials List */}
      <div className="space-y-3">
        {items.map((item) => (
          <MaterialItemRow
            key={item.id}
            item={item}
            formatPrice={formatPrice}
            onBuyClick={handleBuyClick}
            onTogglePurchased={togglePurchased}
          />
        ))}
      </div>

      {/* Summary Card */}
      <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-6">
        <h4 className="font-semibold text-blue-900 mb-4 flex items-center gap-2">
          <CalculatorIcon />
          Cost Summary
        </h4>
        <div className="space-y-3">
          <div className="flex justify-between text-gray-700">
            <span>Total Items:</span>
            <span className="font-medium">{totalCount} materials</span>
          </div>
          <div className="flex justify-between text-gray-700">
            <span>Items Purchased:</span>
            <span className="font-medium text-green-600">
              {purchasedCount} of {totalCount}
            </span>
          </div>
          <div className="border-t border-blue-200 pt-3">
            <div className="flex justify-between text-lg">
              <span className="font-semibold text-blue-900">
                Estimated Tokopedia Total:
              </span>
              <span className="font-bold text-blue-600">
                {formatPrice(totalEstimatedCost)}
              </span>
            </div>
          </div>
        </div>
        <p className="text-xs text-blue-600 mt-4">
          * Prices are estimates based on current Tokopedia listings. Actual prices may vary.
        </p>
      </div>
    </div>
  );
}

/**
 * Individual material item row component
 */
function MaterialItemRow({
  item,
  formatPrice,
  onBuyClick,
  onTogglePurchased,
}: {
  item: ShoppingItem;
  formatPrice: (price: number) => string;
  onBuyClick: (item: ShoppingItem) => void;
  onTogglePurchased: (itemId: string) => void;
}) {
  const hasBuyLink = item.affiliate_url || item.marketplace_url;

  return (
    <div
      className={`flex items-center gap-4 p-4 rounded-lg border transition-all ${
        item.isPurchased
          ? 'bg-green-50 border-green-200'
          : 'bg-white border-gray-200 hover:border-gray-300'
      }`}
    >
      {/* Checkbox */}
      <button
        onClick={() => onTogglePurchased(item.id)}
        className={`flex-shrink-0 w-6 h-6 rounded border-2 flex items-center justify-center transition-colors ${
          item.isPurchased
            ? 'bg-green-500 border-green-500 text-white'
            : 'border-gray-300 hover:border-green-400'
        }`}
        aria-label={item.isPurchased ? 'Mark as not purchased' : 'Mark as purchased'}
      >
        {item.isPurchased && <CheckIcon />}
      </button>

      {/* Item Details - Bilingual Display */}
      <div className="flex-1 min-w-0">
        {/* English name prominently (for international users) */}
        <p
          className={`font-medium truncate ${
            item.isPurchased ? 'text-green-800 line-through' : 'text-gray-900'
          }`}
        >
          {item.english_name || item.material_name}
        </p>
        {/* Indonesian name for Tokopedia search context */}
        {item.english_name && item.english_name !== item.material_name && (
          <p className="text-xs text-gray-500 truncate mt-0.5">
            🛒 Tokopedia: {item.material_name}
          </p>
        )}
        <div className="flex items-center gap-3 text-sm text-gray-600 mt-1">
          <span>
            {item.quantity} {item.unit}
          </span>
          <span className="text-gray-400">|</span>
          <span>{formatPrice(item.unit_price_idr)} / {item.unit}</span>
        </div>
      </div>

      {/* Price & Buy Button */}
      <div className="flex items-center gap-4 flex-shrink-0">
        <div className="text-right">
          <p
            className={`font-semibold ${
              item.isPurchased ? 'text-green-700' : 'text-gray-900'
            }`}
          >
            {formatPrice(item.total_price_idr)}
          </p>
        </div>

        {hasBuyLink ? (
          <button
            onClick={() => onBuyClick(item)}
            disabled={item.isPurchased}
            className={`px-4 py-2 rounded-lg font-medium text-sm transition-colors flex items-center gap-2 ${
              item.isPurchased
                ? 'bg-green-100 text-green-700 cursor-default'
                : 'bg-green-600 text-white hover:bg-green-700 active:bg-green-800'
            }`}
          >
            {item.isPurchased ? (
              <>
                <CheckCircleIcon />
                Purchased
              </>
            ) : (
              <>
                <TokopediaIcon />
                Buy on Tokopedia
              </>
            )}
          </button>
        ) : (
          <span className="text-sm text-gray-400 px-4 py-2">
            No link available
          </span>
        )}
      </div>
    </div>
  );
}

// Icon components
function ShoppingCartIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z"
      />
    </svg>
  );
}

function CheckCircleIcon() {
  return (
    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
      <path
        fillRule="evenodd"
        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
    </svg>
  );
}

function CalculatorIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"
      />
    </svg>
  );
}

function TokopediaIcon() {
  return (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 15h-2v-6h2v6zm4 0h-2v-6h2v6zm1-8H8V7h8v2z" />
    </svg>
  );
}
