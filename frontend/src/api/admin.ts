import api from "@/lib/axios";

export interface AuditLog {
  id: number;
  actor_id: string | null;
  actor_username: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  payload: any;
  ip_address: string | null;
  created_at: string;
}

export interface PaginatedAuditLogs {
  items: AuditLog[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface WorkerStatus {
  status: "online" | "offline";
  queues: {
    feeds: number;
    notifications: number;
    maintenance: number;
  };
}

export interface AuditLogParams {
  actor?: string;
  action?: string;
  resource_type?: string;
  start_date?: string;
  end_date?: string;
  page?: number;
  page_size?: number;
}

export async function getAuditLogs(params: AuditLogParams): Promise<PaginatedAuditLogs> {
  const { data } = await api.get<PaginatedAuditLogs>("/api/v1/admin/audit-logs", { params });
  return data;
}

export async function getWorkerStatus(): Promise<WorkerStatus> {
  const { data } = await api.get<WorkerStatus>("/api/v1/admin/worker-status");
  return data;
}

export async function exportAuditLogsCsv(params: AuditLogParams): Promise<Blob> {
  const { data } = await api.get("/api/v1/admin/audit-logs", {
    params,
    headers: {
      Accept: "text/csv",
    },
    responseType: "blob",
  });
  return data;
}
