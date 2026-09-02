import api from "@/lib/axios";

export interface DashboardStats {
  total_standards: number;
  active_standards: number;
  /** Every purchased standard, including superseded editions. */
  purchased_standards: number;
  /**
   * The purchased subset of `total_standards`. Use this — not
   * `purchased_standards` — whenever a purchase count is shown as a share of
   * the library, since only this one shares that denominator's population.
   */
  purchased_current_standards: number;
  total_feeds: number;
  enabled_feeds: number;
  events_last_7_days: number;
  unread_notifications: number;
}

export async function getDashboardStats(): Promise<DashboardStats> {
  const { data } = await api.get<DashboardStats>("/api/v1/dashboard/stats");
  return data;
}
