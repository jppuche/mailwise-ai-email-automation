// src/components/AppShell.tsx
// Layout principal: sidebar fijo + header fijo + area de contenido scrollable
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import Header from "./Header";

export default function AppShell() {
  return (
    <div className="app-shell">
      <Sidebar />
      <Header />
      <main className="app-shell__content">
        <Outlet />
      </main>
    </div>
  );
}
