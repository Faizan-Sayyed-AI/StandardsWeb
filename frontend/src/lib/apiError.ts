import { isAxiosError } from "axios";

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (!isAxiosError(error)) return fallback;
  const detail: unknown = error.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "detail" in detail && typeof detail.detail === "string") return detail.detail;
  if (Array.isArray(detail)) {
    const messages = detail.flatMap(issue => {
      if (typeof issue?.msg !== "string") return [];
      const field = Array.isArray(issue.loc) ? issue.loc.at(-1) : undefined;
      return [field ? `${String(field).replaceAll("_", " ")} — ${issue.msg}` : issue.msg];
    });
    if (messages.length) return messages.join(". ");
  }
  return fallback;
}
