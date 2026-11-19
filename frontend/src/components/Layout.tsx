import { Suspense, useState } from "react";
import { Outlet } from "react-router-dom";
import { LogOut, Menu, X } from "lucide-react";
import { Sidebar } from "@/components/Sidebar";
import { NotificationBell } from "@/components/NotificationBell";
import { useAuth } from "@/contexts/useAuth";
import { Button } from "@/components/ui/button";
import * as Dialog from "@radix-ui/react-dialog";
import { cn } from "@/lib/utils";

export function Layout() {
  const { logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    return localStorage.getItem("sidebar_collapsed") !== "false";
  });

  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("sidebar_collapsed", String(next));
      return next;
    });
  };

  return (
    <div className="flex min-h-dvh">
      <div className={cn("sticky top-0 hidden h-dvh shrink-0 lg:block", sidebarCollapsed ? "w-16" : "w-60")}>
        <Sidebar collapsed={sidebarCollapsed} onToggle={toggleSidebar} />
      </div>
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-2 border-b bg-card px-4 shadow-sm sm:px-6">
          <div className="flex items-center gap-2">
            <Dialog.Root open={menuOpen} onOpenChange={setMenuOpen}>
              <Dialog.Trigger asChild><Button size="icon" variant="ghost" className="lg:hidden" aria-label="Open navigation"><Menu size={20} /></Button></Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 z-40 bg-foreground/35" />
                <Dialog.Content aria-describedby={undefined} className="fixed inset-y-0 left-0 z-50 w-72 max-w-[90vw]">
                  <Dialog.Title className="sr-only">Navigation</Dialog.Title>
                  <Sidebar collapsed={false} onNavigate={() => setMenuOpen(false)} />
                  <Dialog.Close asChild><Button size="icon" variant="ghost" aria-label="Close navigation" className="absolute right-2 top-3"><X size={18} /></Button></Dialog.Close>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
            <span className="text-sm font-semibold">StandardSphere</span>
          </div>
          <div className="flex items-center gap-2">
            <NotificationBell />
            <Button variant="ghost" onClick={logout}><LogOut size={16} /><span className="ml-2">Sign out</span></Button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1920px] p-4 sm:p-6 xl:p-8">
          <Suspense fallback={<p role="status" className="text-sm text-muted-foreground">Loading…</p>}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
