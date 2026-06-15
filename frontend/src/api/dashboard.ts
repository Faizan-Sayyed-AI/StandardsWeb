import api from "@/lib/axios";

export interface DashboardStats {
  total_standards: number;
  active_standards: number;
  purchased_standards: number;
  total_feeds: number;
  enabled_feeds: number;
  events_last_7_days: number;
  unread_notifications: number;
}

export async function getDashboardStats(): Promise<DashboardStats> {
  const { data } = await api.get<DashboardStats>("/api/v1/dashboard/stats");
  return data;
}
