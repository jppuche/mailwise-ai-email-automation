// src/pages/NotFoundPage.tsx
import { Link } from "react-router-dom";
import { FileQuestion } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4 text-center animate-in fade-in slide-in-from-bottom-2 duration-300 fill-mode-both">
      <FileQuestion className="h-12 w-12 text-muted-foreground" />
      <div className="text-7xl font-bold text-muted-foreground/50">404</div>
      <h1 className="text-2xl font-semibold tracking-tight text-foreground">
        Page not found
      </h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        The page you are looking for does not exist or has been moved.
      </p>
      <Button asChild variant="outline">
        <Link to="/">Go to dashboard</Link>
      </Button>
    </div>
  );
}
