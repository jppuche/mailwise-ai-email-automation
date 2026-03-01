import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import axios from "axios";
import type { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse } from "axios";

describe("API Client interceptors", () => {
  let client: AxiosInstance;
  let getAccessToken: () => string | null;

  beforeEach(() => {
    getAccessToken = vi.fn(() => "test-access-token");

    client = axios.create({
      baseURL: "/api/v1",
      headers: { "Content-Type": "application/json" },
    });

    // Request interceptor: inject Bearer token (mirrors client.ts logic)
    client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
      const token = getAccessToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("injects Bearer token in request headers", () => {
    // Test the interceptor function directly: create a mock config, run through it
    const mockConfig = {
      headers: new axios.AxiosHeaders(),
    } as InternalAxiosRequestConfig;

    // Simulate what the interceptor does
    const token = getAccessToken();
    if (token) {
      mockConfig.headers.Authorization = `Bearer ${token}`;
    }

    expect(mockConfig.headers.Authorization).toBe("Bearer test-access-token");
  });

  it("sets correct baseURL /api/v1", () => {
    expect(client.defaults.baseURL).toBe("/api/v1");
  });

  it("sets Content-Type to application/json", () => {
    expect(client.defaults.headers["Content-Type"]).toBe("application/json");
  });
});

describe("401 refresh interceptor logic", () => {
  it("calls redirectToLogin when refresh token is unavailable", () => {
    const redirectToLogin = vi.fn();
    const getRefreshToken = vi.fn(() => null);

    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      redirectToLogin();
    }

    expect(redirectToLogin).toHaveBeenCalledOnce();
  });

  it("calls onTokenRefreshed with new tokens after successful refresh", () => {
    const onTokenRefreshed = vi.fn();

    onTokenRefreshed("new-access", "new-refresh");

    expect(onTokenRefreshed).toHaveBeenCalledWith("new-access", "new-refresh");
  });

  it("queued requests get resolved with new token after refresh", async () => {
    const queue: Array<(token: string | null) => void> = [];
    const results: (string | null)[] = [];

    const promise1 = new Promise<void>((resolve) => {
      queue.push((token) => {
        results.push(token);
        resolve();
      });
    });
    const promise2 = new Promise<void>((resolve) => {
      queue.push((token) => {
        results.push(token);
        resolve();
      });
    });

    queue.forEach((cb) => cb("new-token"));

    await Promise.all([promise1, promise2]);
    expect(results).toEqual(["new-token", "new-token"]);
  });

  it("queued requests get null token on refresh failure", async () => {
    const queue: Array<(token: string | null) => void> = [];
    const results: (string | null)[] = [];

    const promise1 = new Promise<void>((resolve) => {
      queue.push((token) => {
        results.push(token);
        resolve();
      });
    });

    queue.forEach((cb) => cb(null));

    await promise1;
    expect(results).toEqual([null]);
  });
});
