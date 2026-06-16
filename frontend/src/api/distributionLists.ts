import api from "@/lib/axios";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface DistributionList {
  id: string;
  name: string;
  description: string | null;
  created_by: string | null;
  created_at: string;
  member_count: number;
}

export interface DistributionListMember {
  id: string;
  list_id: string;
  email: string;
  name: string | null;
  is_active: boolean;
}

export interface SMTPConfig {
  SMTP_HOST: string;
  SMTP_PORT: number;
  SMTP_USER: string;
  SMTP_PASSWORD?: string;
  SMTP_USE_TLS: boolean;
  SMTP_FROM_ADDRESS: string;
}

export interface TriggerMapping {
  id: string;
  event_type: string;
  list_id: string;
  notify_all_users: boolean;
  list_name: string | null;
}

// ── Distribution Lists ────────────────────────────────────────────────────────

export async function listDistributionLists(): Promise<DistributionList[]> {
  const { data } = await api.get<DistributionList[]>("/api/v1/distribution-lists");
  return data;
}

export async function createDistributionList(payload: {
  name: string;
  description?: string | null;
}): Promise<DistributionList> {
  const { data } = await api.post<DistributionList>("/api/v1/distribution-lists", payload);
  return data;
}

export async function updateDistributionList(
  id: string,
  payload: { name?: string; description?: string | null }
): Promise<DistributionList> {
  const { data } = await api.patch<DistributionList>(`/api/v1/distribution-lists/${id}`, payload);
  return data;
}

export async function deleteDistributionList(id: string): Promise<void> {
  await api.delete(`/api/v1/distribution-lists/${id}`);
}

// ── Members ───────────────────────────────────────────────────────────────────

export async function listMembers(listId: string): Promise<DistributionListMember[]> {
  const { data } = await api.get<DistributionListMember[]>(
    `/api/v1/distribution-lists/${listId}/members`
  );
  return data;
}

export async function addMember(
  listId: string,
  payload: { email: string; name?: string | null; is_active?: boolean }
): Promise<DistributionListMember> {
  const { data } = await api.post<DistributionListMember>(
    `/api/v1/distribution-lists/${listId}/members`,
    payload
  );
  return data;
}

export async function removeMember(listId: string, email: string): Promise<void> {
  await api.delete(`/api/v1/distribution-lists/${listId}/members/${email}`);
}

// ── SMTP Settings ─────────────────────────────────────────────────────────────

export async function getSMTPConfig(): Promise<SMTPConfig> {
  const { data } = await api.get<SMTPConfig>("/api/v1/admin/smtp-config");
  return data;
}

export async function updateSMTPConfig(payload: SMTPConfig): Promise<SMTPConfig> {
  const { data } = await api.patch<SMTPConfig>("/api/v1/admin/smtp-config", payload);
  return data;
}

// ── Trigger Mappings ──────────────────────────────────────────────────────────

export async function listTriggerMappings(): Promise<TriggerMapping[]> {
  const { data } = await api.get<TriggerMapping[]>("/api/v1/admin/trigger-mappings");
  return data;
}

export async function createTriggerMapping(payload: {
  event_type: string;
  list_id: string;
  notify_all_users?: boolean;
}): Promise<TriggerMapping> {
  const { data } = await api.post<TriggerMapping>("/api/v1/admin/trigger-mappings", payload);
  return data;
}

export async function deleteTriggerMapping(id: string): Promise<void> {
  await api.delete(`/api/v1/admin/trigger-mappings/${id}`);
}
