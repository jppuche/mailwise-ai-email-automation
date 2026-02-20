// src/pages/LoginPage.tsx
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

export default function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Si ya autenticado: redirigir
  React.useEffect(() => {
    if (isAuthenticated) {
      navigate("/", { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await login(email, password);
      navigate("/", { replace: true });
    } catch {
      setError("Invalid email or password. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-card__header">
          <div className="login-card__logo">mailwise</div>
          <div className="login-card__subtitle">Intelligent email classification</div>
        </div>

        {error !== null && (
          <div className="login-card__error" role="alert">
            {error}
          </div>
        )}

        <form onSubmit={(e) => { void handleSubmit(e); }} noValidate>
          <div className="form-group">
            <label className="form-label" htmlFor="email">
              Email address
            </label>
            <input
              id="email"
              type="email"
              className="form-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              disabled={isLoading}
              placeholder="you@example.com"
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              disabled={isLoading}
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            className="btn btn--primary"
            disabled={isLoading || email.trim() === "" || password.trim() === ""}
          >
            {isLoading ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
