export interface QueuedToast {
  id: string;
  title?: string;
  description: string;
  variant?: "default" | "destructive";
}

export const MAX_TOASTS = 5;

export function pushToast(prev: QueuedToast[], next: QueuedToast): QueuedToast[] {
  // Deduplicate ONLY error toasts. Background pollers retrying against a failing
  // API emit identical destructive toasts that must not stack up. User-action
  // toasts (default variant) are never deduped, so two real actions that produce
  // the same message (e.g. deleting two standards) both get their confirmation.
  if (next.variant === "destructive") {
    const isDuplicate = prev.some(
      (t) =>
        t.variant === "destructive" &&
        t.title === next.title &&
        t.description === next.description
    );
    if (isDuplicate) {
      return prev;
    }
  }
  return [...prev, next].slice(-MAX_TOASTS);
}
