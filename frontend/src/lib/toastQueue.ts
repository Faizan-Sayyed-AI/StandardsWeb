export interface QueuedToast {
  id: string;
  title?: string;
  description: string;
  variant?: "default" | "destructive";
}

export const MAX_TOASTS = 5;

export function pushToast(prev: QueuedToast[], next: QueuedToast): QueuedToast[] {
  const isDuplicate = prev.some(
    (t) =>
      t.title === next.title &&
      t.description === next.description &&
      t.variant === next.variant
  );
  if (isDuplicate) {
    return prev;
  }
  return [...prev, next].slice(-MAX_TOASTS);
}
