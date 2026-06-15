import api from "@/lib/axios";
import type { Page } from "@/api/standards";

export interface Feed {
  id: string;
  name: string;
  url: string;
  tc_committee: string | null;
  schedule_type: "daily" | "weekly";
  schedule_hour: number;
  schedule_day_of_week: number | null;
  is_enabled: boolean;
  last_polled_at: string | null;
  last_poll_status: string;
  failure_count: number;
  created_by: string | null;
  created_at: string;
}

export interface FeedCreate {
  name: string;
  url: string;
  tc_committee?: string;
  schedule_type: "daily" | "weekly";
  schedule_hour: number;
  schedule_day_of_week?: number;
  is_enabled: boolean;
}

export interface FeedUpdate extends Partial<FeedCreate> {}

export async function listFeeds(page = 1, pageSize = 20): Promise<Page<Feed>> {
  const { data } = await api.get<Page<Feed>>("/api/v1/feeds", {
    params: { page, page_size: pageSize },
  });
  return data;
}

export async function createFeed(payload: FeedCreate): Promise<Feed> {
  const { data } = await api.post<Feed>("/api/v1/feeds", payload);
  return data;
}

export async function updateFeed(id: string, payload: FeedUpdate): Promise<Feed> {
  const { data } = await api.patch<Feed>(`/api/v1/feeds/${id}`, payload);
  return data;
}

export async function deleteFeed(id: string): Promise<void> {
  await api.delete(`/api/v1/feeds/${id}`);
}

export async function triggerPoll(id: string): Promise<{ task_id: string; message: string }> {
  const { data } = await api.post(`/api/v1/feeds/${id}/poll`);
  return data;
}
