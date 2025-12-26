/**
 * React hook for cost estimation functionality
 */

import { useState, useEffect } from "react";
import { estimatesApi, type CreateEstimateRequest } from "../api/estimates";
import type { EstimateResponse, EstimateStatus } from "../types";

interface UseEstimateResult {
  estimate: EstimateResponse | null;
  loading: boolean;
  error: string | null;
  progress: number;
  progressMessage: string | null;
  createEstimate: (request: CreateEstimateRequest) => Promise<void>;
  pollStatus: (estimateId: string) => Promise<void>;
  reset: () => void;
}

const POLL_INTERVAL = 2000; // Poll every 2 seconds
const MAX_POLL_ATTEMPTS = 30; // Max 60 seconds of polling

export function useEstimate(): UseEstimateResult {
  const [estimate, setEstimate] = useState<EstimateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState<string | null>(null);
  const [pollAttempts, setPollAttempts] = useState(0);

  const createEstimate = async (request: CreateEstimateRequest) => {
    setLoading(true);
    setError(null);
    setProgress(0);
    setProgressMessage(null);

    const response = await estimatesApi.create(request);

    if (response.error) {
      setError(response.error.message);
      setLoading(false);
    } else if (response.data) {
      setEstimate(response.data);

      // Start polling if status is PENDING or PROCESSING
      if (
        response.data.status === "pending" ||
        response.data.status === "processing"
      ) {
        pollStatus(response.data.estimate_id);
      } else {
        setLoading(false);
      }
    }
  };

  const pollStatus = async (estimateId: string) => {
    if (pollAttempts >= MAX_POLL_ATTEMPTS) {
      setError("Estimate processing timeout. Please try again.");
      setLoading(false);
      return;
    }

    const response = await estimatesApi.getStatus(estimateId);

    if (response.error) {
      setError(response.error.message);
      setLoading(false);
      return;
    }

    if (response.data) {
      setProgress(response.data.progress_percentage);
      setProgressMessage(response.data.message);

      if (response.data.status === "completed" || response.data.status === "failed") {
        // Fetch full details
        const detailsResponse = await estimatesApi.getDetails(estimateId);
        if (detailsResponse.data) {
          setEstimate(detailsResponse.data);
        }
        setLoading(false);
      } else {
        // Continue polling
        setPollAttempts((prev) => prev + 1);
        setTimeout(() => pollStatus(estimateId), POLL_INTERVAL);
      }
    }
  };

  const reset = () => {
    setEstimate(null);
    setError(null);
    setLoading(false);
    setProgress(0);
    setProgressMessage(null);
    setPollAttempts(0);
  };

  return { estimate, loading, error, progress, progressMessage, createEstimate, pollStatus, reset };
}
