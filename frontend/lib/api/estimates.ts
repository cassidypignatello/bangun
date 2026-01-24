/**
 * Cost estimation API methods
 */

import { apiClient } from "./client";
import type {
  EstimateResponse,
  EstimateStatusResponse,
  ApiResponse,
} from "../types";

export interface CreateEstimateRequest {
  description: string;
  images?: string[];
}

export const estimatesApi = {
  /**
   * Create a new cost estimate
   * POST /estimates
   */
  create: async (
    request: CreateEstimateRequest
  ): Promise<ApiResponse<EstimateResponse>> => {
    return apiClient.post<EstimateResponse, CreateEstimateRequest>(
      "/estimates",
      request
    );
  },

  /**
   * Get estimate status (for polling during processing)
   * GET /estimates/{id}/status
   */
  getStatus: async (
    estimateId: string
  ): Promise<ApiResponse<EstimateStatusResponse>> => {
    return apiClient.get<EstimateStatusResponse>(
      `/estimates/${estimateId}/status`
    );
  },

  /**
   * Get complete estimate details
   * GET /estimates/{id}
   */
  getDetails: async (
    estimateId: string
  ): Promise<ApiResponse<EstimateResponse>> => {
    return apiClient.get<EstimateResponse>(`/estimates/${estimateId}`);
  },
};
