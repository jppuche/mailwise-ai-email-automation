// src/components/Sidebar.tsx
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

interface NavItem {
  path: string;
  label: string;
  icon: string;
  adminOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { path: "/",             label: "Overview",        icon: "◈" },
  { path: "/emails",       label: "Emails",          icon: "✉" },
  { path: "/review",       label: "Review Queue",    icon: "◎" },
  { path: "/routing",      label: "Routing Rules",   icon: "⇒" },
  { path: "/analytics",    label: "Analytics",       icon: "◉" },
];

const ADMIN_NAV_ITEMS: NavItem[] = [
  { path: "/classification", label: "Classification", icon: "⊞", adminOnly: true },
  { path: "/integrations",   label: "Integrations",  icon: "⊕", adminOnly: true },
  { path: "/logs",           label: "Logs",           icon: "≡",  adminOnly: true },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async (): Promise<void> => {
    await logout();
    navigate("/login", { replace: true });
  };

  const initials = user?.email.charAt(0).toUpperCase() ?? "?";

  return (
    <aside className="sidebar">
      <div className="sidebar__logo">
        <span className="sidebar__logo-text">mailwise</span>
      </div>

      <nav className="sidebar__nav" aria-label="Main navigation">
        <span className="sidebar__nav-label">Workspace</span>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === "/"}
            className={({ isActive }) =>
              `sidebar__link${isActive ? " sidebar__link--active" : ""}`
            }
          >
            <span className="sidebar__link-icon" aria-hidden="true">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}

        {user?.role === "Admin" && (
          <>
            <span className="sidebar__nav-label" style={{ marginTop: "0.5rem" }}>Admin</span>
            {ADMIN_NAV_ITEMS.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `sidebar__link${isActive ? " sidebar__link--active" : ""}`
                }
              >
                <span className="sidebar__link-icon" aria-hidden="true">{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </>
        )}
      </nav>

      <div className="sidebar__footer">
        <div className="sidebar__user">
          <div className="sidebar__user-avatar" aria-hidden="true">{initials}</div>
          <div className="sidebar__user-info">
            <div className="sidebar__user-email" title={user?.email ?? ""}>{user?.email}</div>
            <div className="sidebar__user-role">{user?.role}</div>
          </div>
        </div>
        <button
          className="sidebar__link"
          onClick={() => { void handleLogout(); }}
          style={{ marginTop: "0.5rem", color: "var(--color-error)" }}
          aria-label="Sign out"
        >
          <span className="sidebar__link-icon" aria-hidden="true">⏻</span>
          Sign out
        </button>
      </div>
    </aside>
  );
}
