/**
 * Type-safe API client for Bangun backend
 * Handles authentication, error handling, and request/response transformation
 */

import type { ApiResponse, ApiError } from "../types";

class ApiClient {
  private baseURL: string;

  constructor(baseURL?: string) {
    this.baseURL = baseURL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  }

  /**
   * Generic fetch wrapper with error handling and type safety
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const url = `${this.baseURL}${endpoint}`;

    const config: RequestInit = {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    };

    try {
      const response = await fetch(url, config);

      // Handle non-JSON responses
      const contentType = response.headers.get("content-type");
      if (!contentType?.includes("application/json")) {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        // For successful non-JSON responses, return empty data
        return { data: {} as T };
      }

      const data = await response.json();

      if (!response.ok) {
        const error: ApiError = {
          message: data.detail || data.message || `HTTP ${response.status}`,
          code: data.code || `HTTP_${response.status}`,
          details: data,
        };
        return { error };
      }

      return { data };
    } catch (error) {
      const apiError: ApiError = {
        message: error instanceof Error ? error.message : "Unknown error occurred",
        code: "NETWORK_ERROR",
        details: error,
      };
      return { error: apiError };
    }
  }

  /**
   * GET request
   */
  async get<T>(endpoint: string, params?: Record<string, string>): Promise<ApiResponse<T>> {
    const queryString = params
      ? `?${new URLSearchParams(params).toString()}`
      : "";
    return this.request<T>(`${endpoint}${queryString}`, {
      method: "GET",
    });
  }

  /**
   * POST request
   */
  async post<T, B = unknown>(
    endpoint: string,
    body?: B
  ): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  /**
   * PUT request
   */
  async put<T, B = unknown>(
    endpoint: string,
    body?: B
  ): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  /**
   * DELETE request
   */
  async delete<T>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: "DELETE",
    });
  }

  /**
   * Update base URL (useful for testing or dynamic API endpoints)
   */
  setBaseURL(url: string): void {
    this.baseURL = url;
  }

  /**
   * Get current base URL
   */
  getBaseURL(): string {
    return this.baseURL;
  }
}

// Export singleton instance
export const apiClient = new ApiClient();

// Also export the class for testing or custom instances
export { ApiClient };
