import api from "@/lib/axios";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Standard {
  id: string;
  iso_reference: string;
  title: string;
  edition: string | null;
  tc_committee: string | null;
  status: string;
  is_purchased: boolean;
  updated_at: string;
  created_at: string;
}

export interface StandardDetail extends Standard {
  purchased_at: string | null;
  purchase_notes: string | null;
  external_url: string | null;
  source_feed_id: string | null;
}

export interface HistoryItem {
  id: string;
  standard_id: string;
  event_type: string;
  source: string;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown>;
  triggered_by: string | null;
  notes: string | null;
  created_at: string;
}

export interface StandardsListParams {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  tc_committee?: string;
  is_purchased?: boolean;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}

export async function listStandards(params: StandardsListParams = {}): Promise<Page<Standard>> {
  const { data } = await api.get<Page<Standard>>("/api/v1/standards", { params });
  return data;
}

export async function getStandard(id: string): Promise<StandardDetail> {
  const { data } = await api.get<StandardDetail>(`/api/v1/standards/${id}`);
  return data;
}

export async function getStandardHistory(
  id: string,
  page = 1,
  pageSize = 20
): Promise<Page<HistoryItem>> {
  const { data } = await api.get<Page<HistoryItem>>(`/api/v1/standards/${id}/history`, {
    params: { page, page_size: pageSize },
  });
  return data;
}
