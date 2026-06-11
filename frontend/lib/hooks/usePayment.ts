/**
 * React hook for payment and unlock functionality
 */

import { useState } from "react";
import { paymentsApi } from "../api";
import type { UnlockRequest, UnlockResponse, PaymentMethod } from "../types";

/**
 * localStorage key for the email captured during the unlock flow.
 *
 * INTERIM identity mechanism until real auth exists: the backend scopes
 * unlock records per user_email, and the frontend has no auth/session.
 * The PaymentModal captures the buyer's email, initiateUnlock persists it
 * here, and checkUnlockStatus reads it back so unlock status is scoped to
 * this user on this browser.
 */
export const UNLOCK_EMAIL_STORAGE_KEY = "unlock_user_email";

function readStoredUnlockEmail(): string | null {
  try {
    return window.localStorage.getItem(UNLOCK_EMAIL_STORAGE_KEY);
  } catch {
    return null; // localStorage unavailable (SSR, privacy mode)
  }
}

interface UsePaymentResult {
  unlockResponse: UnlockResponse | null;
  loading: boolean;
  error: string | null;
  initiateUnlock: (
    workerId: string,
    paymentMethod: PaymentMethod,
    userEmail: string
  ) => Promise<void>;
  checkUnlockStatus: (workerId: string) => Promise<boolean>;
  reset: () => void;
}

export function usePayment(): UsePaymentResult {
  const [unlockResponse, setUnlockResponse] = useState<UnlockResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const initiateUnlock = async (
    workerId: string,
    paymentMethod: PaymentMethod,
    userEmail: string
  ) => {
    setLoading(true);
    setError(null);

    // Persist the buyer's email so checkUnlockStatus can identify this
    // user later (interim until real auth — see UNLOCK_EMAIL_STORAGE_KEY).
    try {
      window.localStorage.setItem(UNLOCK_EMAIL_STORAGE_KEY, userEmail);
    } catch {
      // localStorage unavailable — unlock still proceeds, but status
      // checks on this browser won't find the email afterwards.
    }

    const returnUrl = `${window.location.origin}/workers/${workerId}`;

    const request: UnlockRequest = {
      worker_id: workerId,
      payment_method: paymentMethod,
      return_url: returnUrl,
    };

    const response = await paymentsApi.unlockWorker(request);

    if (response.error) {
      setError(response.error.message);
      setUnlockResponse(null);
    } else if (response.data) {
      setUnlockResponse(response.data);
      // Redirect to payment URL
      window.location.href = response.data.payment_url;
    }

    setLoading(false);
  };

  const checkUnlockStatus = async (workerId: string): Promise<boolean> => {
    const userEmail = readStoredUnlockEmail();
    if (!userEmail) {
      // No identity on this browser — treat as locked rather than asking
      // the backend an unanswerable question.
      return false;
    }
    const response = await paymentsApi.checkUnlockStatus(workerId, userEmail);
    return response.data?.unlocked ?? false;
  };

  const reset = () => {
    setUnlockResponse(null);
    setError(null);
    setLoading(false);
  };

  return {
    unlockResponse,
    loading,
    error,
    initiateUnlock,
    checkUnlockStatus,
    reset,
  };
}
