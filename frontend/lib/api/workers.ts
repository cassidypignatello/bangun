/**
 * Worker search and discovery API methods
 */

import { apiClient } from "./client";
import type {
  WorkerSearchRequest,
  WorkerSearchResponse,
  WorkerPreview,
  WorkerFullDetails,
  ApiResponse,
} from "../types";

export const workersApi = {
  /**
   * Search for workers based on project requirements
   * POST /workers/search
   */
  search: async (
    request: WorkerSearchRequest
  ): Promise<ApiResponse<WorkerSearchResponse>> => {
    return apiClient.post<WorkerSearchResponse, WorkerSearchRequest>(
      "/workers/search",
      request
    );
  },

  /**
   * Get worker preview (masked contact info)
   * GET /workers/{id}/preview
   */
  getPreview: async (workerId: string): Promise<ApiResponse<WorkerPreview>> => {
    return apiClient.get<WorkerPreview>(`/workers/${workerId}/preview`);
  },

  /**
   * Get full worker details (requires unlock via payment)
   * GET /workers/{id}/detail
   */
  getDetails: async (
    workerId: string
  ): Promise<ApiResponse<WorkerFullDetails>> => {
    return apiClient.get<WorkerFullDetails>(`/workers/${workerId}/details`);
  },
};
