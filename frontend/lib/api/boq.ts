/**
 * BoQ (Bill of Quantity) API client
 * Handles file uploads and analysis status/results
 */

import type { ApiResponse } from "../types";

// Types matching backend schemas
export type BoQJobStatus = 'pending' | 'processing' | 'completed' | 'failed';
export type BoQFileFormat = 'pdf' | 'xlsx' | 'xls';
export type BoQItemType = 'material' | 'labor' | 'equipment' | 'unknown';

export interface BoQUploadResponse {
  job_id: string;
  status: BoQJobStatus;
  message: string;
  ok: boolean;
}

export interface BoQJobStatusResponse {
  job_id: string;
  status: BoQJobStatus;
  progress_percent: number;
  message?: string;
  error_message?: string;
  total_items_extracted: number;
  materials_count: number;
  labor_count: number;
  owner_supply_count: number;
  created_at: string;
  completed_at?: string;
}

export interface BoQItemPriced {
  id: string;
  section?: string;
  item_number?: string;
  description: string;
  unit?: string;
  quantity?: number;
  contractor_unit_price?: number;
  contractor_total?: number;
  item_type: BoQItemType;
  is_owner_supply: boolean;
  is_existing: boolean;
  extraction_confidence: number;
  // Pricing fields
  search_query?: string;
  tokopedia_product_name?: string;
  tokopedia_price?: number;
  tokopedia_url?: string;
  tokopedia_seller?: string;
  tokopedia_seller_location?: string;
  match_confidence?: number;
  market_unit_price?: number;
  market_total?: number;
  price_difference?: number;
  price_difference_percent?: number;
}

export interface BoQSummary {
  contractor_total: number;
  market_estimate: number;
  potential_savings: number;
  savings_percent: number;
  total_items: number;
  materials_count: number;
  labor_count: number;
  owner_supply_count: number;
  priced_count: number;
}

export interface BoQMetadata {
  project_name?: string;
  contractor_name?: string;
  project_location?: string;
  filename: string;
}

export interface BoQAnalysisResults {
  job_id: string;
  status: BoQJobStatus;
  metadata: BoQMetadata;
  summary: BoQSummary;
  owner_supply_items: BoQItemPriced[];
  overpriced_items: BoQItemPriced[];
  all_materials: BoQItemPriced[];
  labor_items: BoQItemPriced[];
  completed_at?: string;
}

class BoQApi {
  private baseURL: string;

  constructor() {
    this.baseURL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  }

  /**
   * Upload a BoQ file for analysis
   */
  async uploadFile(file: File, sessionId?: string): Promise<ApiResponse<BoQUploadResponse>> {
    const formData = new FormData();
    formData.append('file', file);

    const headers: Record<string, string> = {};
    if (sessionId) {
      headers['X-Session-ID'] = sessionId;
    }

    try {
      const response = await fetch(`${this.baseURL}/api/v1/boq/upload`, {
        method: 'POST',
        headers,
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        return {
          error: {
            message: data.detail || `Upload failed: ${response.status}`,
            code: `HTTP_${response.status}`,
            details: data,
          },
        };
      }

      return { data };
    } catch (error) {
      return {
        error: {
          message: error instanceof Error ? error.message : 'Upload failed',
          code: 'NETWORK_ERROR',
          details: error,
        },
      };
    }
  }

  /**
   * Get job status and progress
   */
  async getStatus(jobId: string): Promise<ApiResponse<BoQJobStatusResponse>> {
    try {
      const response = await fetch(`${this.baseURL}/api/v1/boq/${jobId}/status`);
      const data = await response.json();

      if (!response.ok) {
        return {
          error: {
            message: data.detail || `Status check failed: ${response.status}`,
            code: `HTTP_${response.status}`,
            details: data,
          },
        };
      }

      return { data };
    } catch (error) {
      return {
        error: {
          message: error instanceof Error ? error.message : 'Status check failed',
          code: 'NETWORK_ERROR',
          details: error,
        },
      };
    }
  }

  /**
   * Get full analysis results (only available when status is 'completed')
   */
  async getResults(jobId: string): Promise<ApiResponse<BoQAnalysisResults>> {
    try {
      const response = await fetch(`${this.baseURL}/api/v1/boq/${jobId}/results`);
      const data = await response.json();

      if (!response.ok) {
        return {
          error: {
            message: data.detail || `Results fetch failed: ${response.status}`,
            code: `HTTP_${response.status}`,
            details: data,
          },
        };
      }

      return { data };
    } catch (error) {
      return {
        error: {
          message: error instanceof Error ? error.message : 'Results fetch failed',
          code: 'NETWORK_ERROR',
          details: error,
        },
      };
    }
  }
}

// Export singleton instance
export const boqApi = new BoQApi();
