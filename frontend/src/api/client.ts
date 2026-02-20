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
  baseURL: "/api",
  withCredentials: true, // envia la cookie httpOnly de refresh en cross-origin dev
  headers: {
    "Content-Type": "application/json",
  },
});

// Referencia a getAccessToken — se setea desde AuthProvider para evitar circular dep
let _getAccessToken: (() => string | null) | null = null;
let _redirectToLogin: (() => void) | null = null;
let _isRefreshing = false;
let _refreshQueue: Array<(token: string | null) => void> = [];

export function configureClient(
  getToken: () => string | null,
  redirectFn: () => void,
): void {
  _getAccessToken = getToken;
  _redirectToLogin = redirectFn;
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
      const { data } = await apiClient.post<{ access_token: string }>("/auth/refresh");
      const newToken = data.access_token;
      _refreshQueue.forEach((cb) => cb(newToken));
      _refreshQueue = [];
      if (originalRequest.headers) {
        originalRequest.headers["Authorization"] = `Bearer ${newToken}`;
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
