import React, { createContext, useContext, useState, useCallback } from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { X } from "lucide-react";

interface ToastMessage {
  id: string;
  title?: string;
  description: string;
  variant?: "default" | "destructive";
}

interface ToastContextType {
  toast: (message: Omit<ToastMessage, "id">) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const toast = useCallback(({ title, description, variant = "default" }: Omit<ToastMessage, "id">) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, title, description, variant }]);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  React.useEffect(() => {
    const handleApiError = (e: Event) => {
      const customEvent = e as CustomEvent<{ detail: string; code: string }>;
      const { detail, code } = customEvent.detail;
      toast({
        title: code ? code.replace(/_/g, " ") : "Error",
        description: detail || "An unexpected error occurred",
        variant: "destructive",
      });
    };
    window.addEventListener("api-error", handleApiError);
    return () => window.removeEventListener("api-error", handleApiError);
  }, [toast]);

  return (
    <ToastContext.Provider value={{ toast }}>
      <ToastPrimitive.Provider swipeDirection="right" duration={4000}>
        {children}
        
        {toasts.map(({ id, title, description, variant }) => (
          <ToastPrimitive.Root
            key={id}
            open
            onOpenChange={(open) => {
              if (!open) removeToast(id);
            }}
            className={`flex w-full max-w-sm items-start gap-3 rounded-xl border p-4 shadow-2xl transition-all duration-300 data-[state=open]:animate-in data-[state=closed]:animate-out ${
              variant === "destructive"
                ? "bg-red-950/95 border-red-500/30 text-red-200"
                : "bg-slate-900/95 border-white/10 text-slate-100"
            }`}
          >
            <div className="flex-1 space-y-1">
              {title && <ToastPrimitive.Title className="text-sm font-semibold tracking-tight">{title}</ToastPrimitive.Title>}
              <ToastPrimitive.Description className="text-xs opacity-90 leading-normal">
                {description}
              </ToastPrimitive.Description>
            </div>
            
            <ToastPrimitive.Close className="rounded-lg p-1 text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors">
              <X className="h-4 w-4" />
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        ))}

        <ToastPrimitive.Viewport className="fixed bottom-0 right-0 z-50 m-4 flex flex-col gap-3 w-full max-w-sm outline-none" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}
