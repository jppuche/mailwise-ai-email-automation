// src/contexts/AuthContext.tsx
import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { loginRequest, refreshRequest, logoutRequest, getMeRequest } from "@/api/auth";
import { configureClient } from "@/api/client";

// AuthUser: estado interno de AuthContext.
// Derivado de UserResponse del schema generado — no duplica la definicion completa.
// Roles son lowercase ("admin" | "reviewer") — match con UserRole del backend.
export interface AuthUser {
  id: string;
  username: string;
  role: "admin" | "reviewer";
}

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  getAccessToken: () => string | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function getTokenExpSeconds(token: string): number {
  const parts = token.split(".");
  if (parts.length !== 3) return 0;
  const payload: { exp?: number } = JSON.parse(atob(parts[1]));
  if (typeof payload.exp !== "number") return 0;
  return payload.exp - Math.floor(Date.now() / 1000);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  // Access token y refresh token en memoria — NUNCA en localStorage (proteccion contra XSS)
  const accessTokenRef = useRef<string | null>(null);
  const refreshTokenRef = useRef<string | null>(null);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearAuth = useCallback((): void => {
    accessTokenRef.current = null;
    refreshTokenRef.current = null;
    setUser(null);
    if (refreshTimerRef.current !== null) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const scheduleRefresh = useCallback((accessToken: string): void => {
    const expiresInSeconds = getTokenExpSeconds(accessToken);
    // Refrescar 30s antes de la expiracion
    const delay = Math.max(0, (expiresInSeconds - 30) * 1000);
    if (refreshTimerRef.current !== null) {
      clearTimeout(refreshTimerRef.current);
    }
    refreshTimerRef.current = setTimeout(async () => {
      try {
        const currentRefreshToken = refreshTokenRef.current;
        if (!currentRefreshToken) {
          clearAuth();
          return;
        }
        const response = await refreshRequest({ refresh_token: currentRefreshToken });
        accessTokenRef.current = response.access_token;
        refreshTokenRef.current = response.refresh_token;
        scheduleRefresh(response.access_token);
      } catch {
        // Refresh fallido: limpiar estado
        clearAuth();
      }
    }, delay);
  }, [clearAuth]);

  const login = useCallback(async (username: string, password: string): Promise<void> => {
    // Estado externo — try/catch delegado al caller (LoginPage.tsx)
    const tokenResponse = await loginRequest({ username, password });
    accessTokenRef.current = tokenResponse.access_token;
    refreshTokenRef.current = tokenResponse.refresh_token;

    // Fetch user info from /auth/me (TokenResponse no incluye user data)
    const userInfo = await getMeRequest();
    setUser({
      id: userInfo.id,
      username: userInfo.username,
      role: userInfo.role,
    });
    scheduleRefresh(tokenResponse.access_token);
  }, [scheduleRefresh]);

  const logout = useCallback(async (): Promise<void> => {
    try {
      const currentRefreshToken = refreshTokenRef.current;
      if (currentRefreshToken) {
        await logoutRequest(currentRefreshToken);
      }
    } finally {
      // Limpiar estado local independientemente del resultado del servidor
      clearAuth();
    }
  }, [clearAuth]);

  const getAccessToken = useCallback((): string | null => accessTokenRef.current, []);

  // Configurar el api client y resolver loading al montar
  useEffect(() => {
    configureClient({
      getAccessToken: () => accessTokenRef.current,
      getRefreshToken: () => refreshTokenRef.current,
      onTokenRefreshed: (newAccessToken, newRefreshToken) => {
        accessTokenRef.current = newAccessToken;
        refreshTokenRef.current = newRefreshToken;
      },
      redirectToLogin: () => {
        clearAuth();
        window.location.href = "/login";
      },
    });

    // Sin refresh token al cargar (en memoria, no persiste entre recargas) — no intentar restore
    setIsLoading(false);

    return () => {
      if (refreshTimerRef.current !== null) {
        clearTimeout(refreshTimerRef.current);
      }
    };
  }, [clearAuth]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: user !== null,
        isLoading,
        login,
        logout,
        getAccessToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
