// src/pages/LoginPage.tsx
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Mail, Tags, Route, BarChart3, ShieldCheck } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";

export default function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
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
      await login(username, password);
      navigate("/", { replace: true });
    } catch {
      setError("Invalid username or password. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen animate-in fade-in slide-in-from-bottom-2 duration-300 fill-mode-both">
      {/* Left brand panel — hidden on mobile */}
      <div className="hidden lg:flex lg:w-1/2 flex-col items-center justify-center bg-gradient-to-br from-sidebar to-accent-navy p-12">
        <div className="max-w-md space-y-6 text-center">
          <div className="mx-auto flex size-16 items-center justify-center rounded-2xl bg-primary text-primary-foreground">
            <Mail className="size-8" />
          </div>
          <h1 className="text-4xl font-bold text-primary-foreground tracking-tight">mailwise</h1>
          <p className="text-lg text-primary-foreground/70">
            Intelligent email classification and routing, powered by AI.
          </p>
          <ul className="mt-8 space-y-4 text-left">
            {[
              { icon: Tags, text: "AI-powered classification with configurable actions" },
              { icon: Route, text: "Smart routing to Slack, email, and CRM channels" },
              { icon: BarChart3, text: "Real-time analytics and accuracy tracking" },
              { icon: ShieldCheck, text: "Human-in-the-loop draft review workflow" },
            ].map((item) => (
              <li key={item.text} className="flex items-start gap-3">
                <item.icon className="size-5 shrink-0 text-primary mt-0.5" />
                <span className="text-sm text-primary-foreground/80">{item.text}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Right login form */}
      <div className="flex flex-1 items-center justify-center bg-background px-4">
        <Card className="w-full max-w-sm shadow-[var(--shadow-elevated)]">
          <CardHeader className="space-y-1 pb-0">
            <div className="flex items-center gap-2 lg:hidden">
              <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground text-sm font-bold">
                m
              </div>
              <span className="text-2xl font-bold tracking-tight text-foreground">
                mailwise
              </span>
            </div>
            <div className="hidden lg:block text-2xl font-bold tracking-tight text-foreground">
              Welcome back
            </div>
            <p className="text-sm text-muted-foreground">
              Sign in to your account
            </p>
          </CardHeader>

          <CardContent className="pt-4">
            {error !== null && (
              <Alert variant="destructive" className="mb-4">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <form onSubmit={(e) => { void handleSubmit(e); }} noValidate className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  required
                  disabled={isLoading}
                  placeholder="your-username"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                  disabled={isLoading}
                  placeholder="••••••••"
                />
              </div>

              <Button
                type="submit"
                className="w-full"
                disabled={isLoading || username.trim() === "" || password.trim() === ""}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Signing in...
                  </>
                ) : (
                  "Sign in"
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
