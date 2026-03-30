// src/components/Sidebar.tsx
import { NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Mail,
  ClipboardCheck,
  Route,
  BarChart3,
  Tags,
  Plug,
  ScrollText,
  LogOut,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import {
  Sidebar as SidebarRoot,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
} from "@/components/ui/sidebar";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
}

const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Overview", icon: LayoutDashboard },
  { path: "/emails", label: "Emails", icon: Mail },
  { path: "/review", label: "Review Queue", icon: ClipboardCheck },
  { path: "/routing", label: "Routing Rules", icon: Route },
  { path: "/analytics", label: "Analytics", icon: BarChart3 },
];

const ADMIN_NAV_ITEMS: NavItem[] = [
  { path: "/classification", label: "Classification", icon: Tags },
  { path: "/integrations", label: "Integrations", icon: Plug },
  { path: "/logs", label: "Logs", icon: ScrollText },
];

export default function AppSidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async (): Promise<void> => {
    await logout();
    navigate("/login", { replace: true });
  };

  const initials = user?.username?.charAt(0).toUpperCase() ?? "?";

  return (
    <SidebarRoot>
      <SidebarHeader className="px-4 py-5">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground text-sm font-bold">
            m
          </div>
          <span className="text-lg font-bold text-sidebar-primary-foreground tracking-tight">
            mailwise
          </span>
        </div>
      </SidebarHeader>

      <SidebarSeparator />

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Workspace</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV_ITEMS.map((item) => (
                <SidebarMenuItem key={item.path}>
                  <SidebarMenuButton asChild tooltip={item.label}>
                    <NavLink
                      to={item.path}
                      end={item.path === "/"}
                    >
                      <item.icon />
                      <span>{item.label}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {user?.role === "admin" && (
          <SidebarGroup>
            <SidebarGroupLabel>Admin</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {ADMIN_NAV_ITEMS.map((item) => (
                  <SidebarMenuItem key={item.path}>
                    <SidebarMenuButton asChild tooltip={item.label}>
                      <NavLink to={item.path}>
                        <item.icon />
                        <span>{item.label}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>

      <SidebarFooter>
        <SidebarSeparator />
        <div className="flex items-center gap-3 px-2 py-2">
          <Avatar className="size-8">
            <AvatarFallback className="bg-sidebar-accent text-sidebar-accent-foreground text-xs">
              {initials}
            </AvatarFallback>
          </Avatar>
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-sm font-medium text-sidebar-foreground">
              {user?.username}
            </span>
            <span className="text-xs text-sidebar-foreground/60 capitalize">
              {user?.role}
            </span>
          </div>
        </div>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={() => { void handleLogout(); }}
              tooltip="Sign out"
              className="text-destructive hover:text-destructive hover:bg-destructive/10"
            >
              <LogOut />
              <span>Sign out</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </SidebarRoot>
  );
}
