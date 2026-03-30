// src/pages/ForbiddenPage.tsx
import { Link } from "react-router-dom";
import { ShieldX } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ForbiddenPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4 text-center animate-in fade-in slide-in-from-bottom-2 duration-300 fill-mode-both">
      <ShieldX className="h-12 w-12 text-destructive" />
      <div className="text-7xl font-bold text-muted-foreground/50">403</div>
      <h1 className="text-2xl font-semibold tracking-tight text-foreground">
        Access denied
      </h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        You do not have permission to access this page. Admin role is required.
      </p>
      <Button asChild>
        <Link to="/">Back to dashboard</Link>
      </Button>
    </div>
  );
}
