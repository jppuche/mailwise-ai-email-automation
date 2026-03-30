// src/components/Header.tsx
import { useLocation } from "react-router-dom";
import { Moon, Sun, Search, Bell } from "lucide-react";
import { useTheme } from "@/contexts/ThemeContext";
import { useAuth } from "@/contexts/AuthContext";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const PAGE_TITLES: Record<string, string> = {
  "/": "Overview",
  "/emails": "Emails",
  "/review": "Review Queue",
  "/routing": "Routing Rules",
  "/analytics": "Analytics",
  "/classification": "Classification",
  "/integrations": "Integrations",
  "/logs": "Logs",
};

export default function Header() {
  const { theme, toggleTheme } = useTheme();
  const { user } = useAuth();
  const location = useLocation();

  const pageTitle = PAGE_TITLES[location.pathname] ?? "mailwise";
  const themeLabel = theme === "light" ? "Switch to dark mode" : "Switch to light mode";
  const isOverview = location.pathname === "/";
  const initials = user?.username?.charAt(0).toUpperCase() ?? "?";

  return (
    <header className="flex h-16 shrink-0 items-center gap-2 border-b px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-2 h-4" />

      <div className="flex flex-col">
        {isOverview && user ? (
          <>
            <span className="text-xs text-muted-foreground hidden sm:block">
              mailwise / {pageTitle}
            </span>
            <h1 className="text-lg font-bold tracking-tight">
              Welcome back, {user.username}
            </h1>
          </>
        ) : (
          <h1 className="text-base font-semibold">{pageTitle}</h1>
        )}
      </div>

      <div className="ml-auto flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          aria-label="Search"
          className="hidden sm:inline-flex"
        >
          <Search className="size-4" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          aria-label="Notifications"
          className="relative"
        >
          <Bell className="size-4" />
          <span className="absolute top-1.5 right-1.5 size-2 rounded-full bg-primary" aria-hidden="true" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          onClick={toggleTheme}
          aria-label={themeLabel}
        >
          {theme === "light" ? <Moon className="size-4" /> : <Sun className="size-4" />}
        </Button>

        <Separator orientation="vertical" className="mx-1 h-6 hidden sm:block" />

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="gap-2 px-2 hidden sm:inline-flex">
              <Avatar className="size-7">
                <AvatarFallback className="bg-primary/10 text-primary text-xs font-semibold">
                  {initials}
                </AvatarFallback>
              </Avatar>
              <span className="text-sm font-medium">{user?.username}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem disabled className="text-xs text-muted-foreground">
              {user?.role}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={toggleTheme}>
              {theme === "light" ? "Dark mode" : "Light mode"}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
