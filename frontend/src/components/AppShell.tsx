// src/components/AppShell.tsx
import { Outlet } from "react-router-dom";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import AppSidebar from "./Sidebar";
import Header from "./Header";

export default function AppShell() {
  return (
    <div className="min-h-screen bg-background p-0 md:p-3 lg:p-5">
      <div className="mx-auto max-w-[1440px] flex min-h-screen md:min-h-[calc(100vh-1.5rem)] lg:min-h-[calc(100vh-2.5rem)] overflow-hidden rounded-none md:rounded-2xl lg:rounded-3xl shadow-[var(--shadow-elevated)] bg-card">
        <SidebarProvider>
          <AppSidebar />
          <SidebarInset>
            <Header />
            <div className="flex-1 overflow-y-auto bg-background px-4 py-4 md:px-6 md:py-6">
              <Outlet />
            </div>
          </SidebarInset>
        </SidebarProvider>
      </div>
    </div>
  );
}
