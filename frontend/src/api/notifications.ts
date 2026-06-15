import api from "@/lib/axios";
import type { Page } from "@/api/standards";

export interface Notification {
  id: string;
  event_type: string;
  severity: "info" | "warning" | "critical";
  title: string;
  body: string;
  related_standard_id: string | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationCount {
  unread: number;
}

export async function getUnreadCount(): Promise<NotificationCount> {
  const { data } = await api.get<NotificationCount>("/api/v1/notifications/count");
  return data;
}

export async function listNotifications(
  page = 1,
  pageSize = 20,
  unreadOnly = false
): Promise<Page<Notification>> {
  const { data } = await api.get<Page<Notification>>("/api/v1/notifications", {
    params: { page, page_size: pageSize, unread_only: unreadOnly },
  });
  return data;
}

export async function markRead(id: string): Promise<Notification> {
  const { data } = await api.patch<Notification>(`/api/v1/notifications/${id}/read`);
  return data;
}

export async function markAllRead(): Promise<{ marked: number }> {
  const { data } = await api.post<{ marked: number }>("/api/v1/notifications/mark-all-read");
  return data;
}
