import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Settings } from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

export default function AppShell({ actions, children }: { actions?: ReactNode; children: ReactNode }) {
  return (
    <TooltipProvider>
      <div className="min-h-screen bg-background text-foreground">
        <header className="sticky top-0 z-30 border-b bg-background/80 backdrop-blur">
          <div className="mx-auto flex h-12 max-w-[1200px] items-center justify-between px-4">
            <Link to="/" className="text-sm font-semibold tracking-tight hover:opacity-70">
              Flight Friend
            </Link>
            <div className="flex items-center gap-1">
              {actions}
              <Button asChild variant="ghost" size="icon" aria-label="관리">
                <Link to="/admin">
                  <Settings />
                </Link>
              </Button>
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-[1200px] px-4 py-6">{children}</main>
        <Toaster />
      </div>
    </TooltipProvider>
  );
}
