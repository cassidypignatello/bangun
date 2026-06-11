/**
 * Payment and unlock API methods
 */

import { apiClient } from "./client";
import type {
  UnlockRequest,
  UnlockResponse,
  ApiResponse,
} from "../types";

export const paymentsApi = {
  /**
   * Initiate payment to unlock worker details
   * POST /unlock
   */
  unlockWorker: async (
    request: UnlockRequest
  ): Promise<ApiResponse<UnlockResponse>> => {
    return apiClient.post<UnlockResponse, UnlockRequest>("/unlock", request);
  },

  /**
   * Check if a specific user has already unlocked a worker
   * GET /unlock/status?worker_id={workerId}&user_email={userEmail}
   *
   * user_email is required: unlock records are scoped per user on the
   * backend, so one user's payment never unlocks the worker for others.
   */
  checkUnlockStatus: async (
    workerId: string,
    userEmail: string
  ): Promise<ApiResponse<{ unlocked: boolean; unlocked_at?: string }>> => {
    return apiClient.get(`/unlock/status`, {
      worker_id: workerId,
      user_email: userEmail,
    });
  },
};
