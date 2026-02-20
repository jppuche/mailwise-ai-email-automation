// src/components/Header.tsx
// Sin logica de negocio — layout y toggle de tema solamente
import { useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";

const PAGE_TITLES: Record<string, string> = {
  "/":               "Overview",
  "/emails":         "Emails",
  "/review":         "Review Queue",
  "/routing":        "Routing Rules",
  "/analytics":      "Analytics",
  "/classification": "Classification",
  "/integrations":   "Integrations",
  "/logs":           "Logs",
};

export default function Header() {
  const { user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();

  const pageTitle = PAGE_TITLES[location.pathname] ?? "mailwise";
  const themeIcon = theme === "light" ? "☽" : "☀";
  const themeLabel = theme === "light" ? "Switch to dark mode" : "Switch to light mode";

  return (
    <header className="header">
      <h1 className="header__title">{pageTitle}</h1>

      <div className="header__actions">
        <button
          className="header__theme-toggle"
          onClick={toggleTheme}
          aria-label={themeLabel}
          title={themeLabel}
        >
          {themeIcon}
        </button>

        <div className="header__user">
          <span>{user?.email}</span>
        </div>
      </div>
    </header>
  );
}
