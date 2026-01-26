/**
 * Materials and pricing API methods
 */

import { apiClient } from "./client";
import type { ApiResponse } from "../types";

export interface Material {
  id: string;
  name: string;
  category: string;
  unit: string;
  current_price_idr: number;
  source: string;
  confidence: number;
  last_updated: string;
  marketplace_url?: string;
}

export interface MaterialHistory {
  material_id: string;
  price_history: {
    date: string;
    price_idr: number;
    source: string;
  }[];
}

// =============================================================================
// Direct Price Lookup Types
// =============================================================================

export interface PriceLookupRequest {
  material_name: string;
  quantity?: number;
  unit?: string;
}

export interface PriceLookupResponse {
  material_name: string;
  unit_price_idr: number;
  total_price_idr: number;
  quantity: number;
  unit: string;
  source: string;
  confidence: number;
  marketplace_url: string | null;
  affiliate_url: string | null;
}

export interface BatchPriceLookupRequest {
  materials: PriceLookupRequest[];
}

export interface BatchPriceLookupResponse {
  prices: PriceLookupResponse[];
  total_cost_idr: number;
  items_priced: number;
  cache_hits: number;
  scrape_count: number;
}

export const materialsApi = {
  /**
   * Get materials list with current pricing
   * GET /materials
   */
  list: async (params?: {
    category?: string;
    search?: string;
  }): Promise<ApiResponse<{ materials: Material[] }>> => {
    return apiClient.get<{ materials: Material[] }>("/materials", params);
  },

  /**
   * Get price history for a material
   * GET /materials/{id}/history
   */
  getHistory: async (
    materialId: string
  ): Promise<ApiResponse<MaterialHistory>> => {
    return apiClient.get<MaterialHistory>(`/materials/${materialId}/history`);
  },

  /**
   * Get real-time price for a single material
   * GET /materials/price
   *
   * Checks cache first, scrapes Tokopedia if needed.
   * Perfect for quick price checks like "How much is gypsum board per m²?"
   */
  getPrice: async (
    materialName: string,
    quantity: number = 1,
    unit: string = "pcs"
  ): Promise<ApiResponse<PriceLookupResponse>> => {
    return apiClient.get<PriceLookupResponse>("/materials/price", {
      q: materialName,
      qty: String(quantity),
      unit: unit,
    });
  },

  /**
   * Get prices for multiple materials in one request
   * POST /materials/prices
   *
   * Useful for pricing a list of specific materials.
   * Limited to 20 items per request.
   */
  getPricesBatch: async (
    materials: PriceLookupRequest[]
  ): Promise<ApiResponse<BatchPriceLookupResponse>> => {
    return apiClient.post<BatchPriceLookupResponse, BatchPriceLookupRequest>(
      "/materials/prices",
      { materials }
    );
  },
};
