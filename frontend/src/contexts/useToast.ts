import { createContext, useContext } from "react";
import type { QueuedToast } from "@/lib/toastQueue";
type ToastMessage = QueuedToast;

interface ToastContextType {
  toast: (message: Omit<ToastMessage, "id">) => void;
}

export const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
