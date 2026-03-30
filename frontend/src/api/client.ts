// src/api/client.ts
// Instancia axios singleton — compartida por todos los modulos de api/
import axios, { type AxiosInstance, type AxiosError, type InternalAxiosRequestConfig } from "axios";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

const apiClient: AxiosInstance = axios.create({
  baseURL: "/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

// Referencia a getAccessToken y getRefreshToken — se setean desde AuthProvider para evitar circular dep
let _getAccessToken: (() => string | null) | null = null;
let _getRefreshToken: (() => string | null) | null = null;
let _onTokenRefreshed: ((accessToken: string, refreshToken: string) => void) | null = null;
let _redirectToLogin: (() => void) | null = null;
let _isRefreshing = false;
let _refreshQueue: Array<(token: string | null) => void> = [];

export function configureClient(opts: {
  getAccessToken: () => string | null;
  getRefreshToken: () => string | null;
  onTokenRefreshed: (accessToken: string, refreshToken: string) => void;
  redirectToLogin: () => void;
}): void {
  _getAccessToken = opts.getAccessToken;
  _getRefreshToken = opts.getRefreshToken;
  _onTokenRefreshed = opts.onTokenRefreshed;
  _redirectToLogin = opts.redirectToLogin;
}

// Request interceptor: inyectar Bearer token
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = _getAccessToken?.();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: manejar 401 con refresh y retry
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config;
    if (error.response?.status !== 401 || !originalRequest) {
      return Promise.reject(error);
    }

    // No intentar refresh en el propio endpoint de refresh (evitar loop infinito)
    if (originalRequest.url === "/auth/refresh") {
      return Promise.reject(error);
    }

    if (_isRefreshing) {
      // Cola: esperar al refresh en curso
      return new Promise((resolve, reject) => {
        _refreshQueue.push((token) => {
          if (token && originalRequest.headers) {
            originalRequest.headers["Authorization"] = `Bearer ${token}`;
            resolve(apiClient(originalRequest));
          } else {
            reject(error);
          }
        });
      });
    }

    _isRefreshing = true;
    try {
      const refreshToken = _getRefreshToken?.();
      if (!refreshToken) {
        throw new Error("No refresh token available");
      }
      const { data } = await apiClient.post<{ access_token: string; refresh_token: string; token_type: string }>(
        "/auth/refresh",
        { refresh_token: refreshToken },
      );
      const newAccessToken = data.access_token;
      const newRefreshToken = data.refresh_token;
      _onTokenRefreshed?.(newAccessToken, newRefreshToken);
      _refreshQueue.forEach((cb) => cb(newAccessToken));
      _refreshQueue = [];
      if (originalRequest.headers) {
        originalRequest.headers["Authorization"] = `Bearer ${newAccessToken}`;
      }
      return apiClient(originalRequest);
    } catch (refreshError: unknown) {
      _refreshQueue.forEach((cb) => cb(null));
      _refreshQueue = [];
      _redirectToLogin?.();
      return Promise.reject(refreshError);
    } finally {
      _isRefreshing = false;
    }
  },
);

export default apiClient;
