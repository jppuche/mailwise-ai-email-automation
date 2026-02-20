// src/contexts/AuthContext.tsx
import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { loginRequest, refreshRequest, logoutRequest } from "@/api/auth";
import { configureClient } from "@/api/client";

// AuthUser: estado interno de AuthContext.
// Derivado de UserInfo del schema generado — no duplica la definicion completa.
export interface AuthUser {
  id: string;
  email: string;
  role: "Admin" | "Reviewer";
}

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  getAccessToken: () => string | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  // Access token en memoria — NUNCA en localStorage (proteccion contra XSS)
  const accessTokenRef = useRef<string | null>(null);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleRefresh = (expiresInSeconds: number): void => {
    // Refrescar 30s antes de la expiracion
    const delay = Math.max(0, (expiresInSeconds - 30) * 1000);
    if (refreshTimerRef.current !== null) {
      clearTimeout(refreshTimerRef.current);
    }
    refreshTimerRef.current = setTimeout(async () => {
      try {
        const response = await refreshRequest();
        accessTokenRef.current = response.access_token;
        scheduleRefresh(response.expires_in);
      } catch {
        // Refresh fallido: limpiar estado y redirigir a login
        setUser(null);
        accessTokenRef.current = null;
      }
    }, delay);
  };

  const getAccessToken = (): string | null => accessTokenRef.current;

  const login = async (email: string, password: string): Promise<void> => {
    // Estado externo — try/catch delegado al caller (LoginPage.tsx)
    const response = await loginRequest({ email, password });
    accessTokenRef.current = response.access_token;
    setUser({
      id: response.user.id,
      email: response.user.email,
      role: response.user.role,
    });
    scheduleRefresh(response.expires_in);
  };

  const logout = async (): Promise<void> => {
    try {
      await logoutRequest();
    } finally {
      // Limpiar estado local independientemente del resultado del servidor
      accessTokenRef.current = null;
      setUser(null);
      if (refreshTimerRef.current !== null) {
        clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    }
  };

  // Intentar refresh silencioso al cargar la app (restaurar sesion si existe cookie)
  useEffect(() => {
    const tryRestore = async (): Promise<void> => {
      try {
        const response = await refreshRequest();
        accessTokenRef.current = response.access_token;
        setUser({
          id: response.user.id,
          email: response.user.email,
          role: response.user.role,
        });
        scheduleRefresh(response.expires_in);
      } catch {
        // Sin sesion previa — normal, no es un error
      } finally {
        setIsLoading(false);
      }
    };
    void tryRestore();

    // Configurar el api client con acceso al token y funcion de redirect
    configureClient(getAccessToken, () => {
      setUser(null);
      accessTokenRef.current = null;
      window.location.href = "/login";
    });

    return () => {
      if (refreshTimerRef.current !== null) {
        clearTimeout(refreshTimerRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
