'use client';

import { useState, useCallback, useMemo, useEffect } from 'react';
import type { BOMItem } from '@/lib/types';

/**
 * Shopping item state with purchase tracking
 */
export interface ShoppingItem extends BOMItem {
  /** Unique identifier for the item (index-based) */
  id: string;
  /** Whether user has clicked 'Buy' for this item */
  isPurchased: boolean;
}

/**
 * Shopping progress state and actions
 */
export interface UseMaterialChecklistReturn {
  /** Shopping items with purchase state */
  items: ShoppingItem[];
  /** Number of items marked as purchased */
  purchasedCount: number;
  /** Total number of items */
  totalCount: number;
  /** Progress percentage (0-100) */
  progressPercent: number;
  /** Total estimated cost in IDR */
  totalEstimatedCost: number;
  /** Mark an item as purchased (clicked 'Buy') */
  markAsPurchased: (itemId: string) => void;
  /** Toggle purchase state for an item */
  togglePurchased: (itemId: string) => void;
  /** Reset all items to unpurchased */
  resetProgress: () => void;
  /** Check if all items are purchased */
  isComplete: boolean;
}

/**
 * Create a stable key for matching items across updates.
 * Uses material_name + unit as the unique identifier.
 */
function getItemKey(item: BOMItem): string {
  return `${item.material_name}|${item.unit}`;
}

/**
 * Hook for managing shopping checklist state and progress tracking.
 *
 * Tracks which BOM items the user has clicked "Buy" for,
 * calculates progress percentage, and provides total cost calculation.
 *
 * @param bomItems - Bill of Materials items from the estimate
 * @returns Shopping state and actions
 *
 * @example
 * ```tsx
 * const { items, progressPercent, markAsPurchased, totalEstimatedCost } = useMaterialChecklist(estimate.bom_items);
 *
 * // When user clicks "Buy" button
 * const handleBuy = (item: ShoppingItem) => {
 *   window.open(item.affiliate_url, '_blank');
 *   markAsPurchased(item.id);
 * };
 * ```
 */
export function useMaterialChecklist(bomItems: BOMItem[]): UseMaterialChecklistReturn {
  const [items, setItems] = useState<ShoppingItem[]>([]);

  // Sync items when bomItems changes, preserving isPurchased state
  useEffect(() => {
    setItems((prevItems) => {
      // Build a map of previous purchase states by item key
      const prevPurchaseState = new Map<string, boolean>();
      for (const item of prevItems) {
        prevPurchaseState.set(item.id, item.isPurchased);
      }

      // Track key occurrences to handle duplicate materials (same name + unit)
      const keyOccurrences = new Map<string, number>();

      // Map new bomItems with stable content-based IDs
      return bomItems.map((item) => {
        const baseKey = getItemKey(item);
        const occurrence = keyOccurrences.get(baseKey) ?? 0;
        keyOccurrences.set(baseKey, occurrence + 1);

        // Stable ID: content-based with occurrence suffix for duplicates
        const stableId = occurrence === 0 ? `bom-${baseKey}` : `bom-${baseKey}#${occurrence}`;
        const wasPurchased = prevPurchaseState.get(stableId) ?? false;

        return {
          ...item,
          id: stableId,
          isPurchased: wasPurchased,
        };
      });
    });
  }, [bomItems]);

  // Mark a specific item as purchased
  const markAsPurchased = useCallback((itemId: string) => {
    setItems((prev) =>
      prev.map((item) =>
        item.id === itemId ? { ...item, isPurchased: true } : item
      )
    );
  }, []);

  // Toggle purchase state for an item
  const togglePurchased = useCallback((itemId: string) => {
    setItems((prev) =>
      prev.map((item) =>
        item.id === itemId ? { ...item, isPurchased: !item.isPurchased } : item
      )
    );
  }, []);

  // Reset all items to unpurchased
  const resetProgress = useCallback(() => {
    setItems((prev) =>
      prev.map((item) => ({ ...item, isPurchased: false }))
    );
  }, []);

  // Derived state calculations
  const purchasedCount = useMemo(
    () => items.filter((item) => item.isPurchased).length,
    [items]
  );

  const totalCount = items.length;

  const progressPercent = useMemo(
    () => (totalCount > 0 ? Math.round((purchasedCount / totalCount) * 100) : 0),
    [purchasedCount, totalCount]
  );

  const totalEstimatedCost = useMemo(
    () =>
      items.reduce((sum, item) => {
        const price = Number(item.total_price_idr) || 0;
        return sum + (Number.isFinite(price) ? price : 0);
      }, 0),
    [items]
  );

  const isComplete = purchasedCount === totalCount && totalCount > 0;

  return {
    items,
    purchasedCount,
    totalCount,
    progressPercent,
    totalEstimatedCost,
    markAsPurchased,
    togglePurchased,
    resetProgress,
    isComplete,
  };
}
