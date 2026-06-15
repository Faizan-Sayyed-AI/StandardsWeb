import api from "@/lib/axios";

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export async function loginApi(email: string, password: string): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>("/api/v1/auth/login", { email, password });
  return data;
}

export async function logoutApi(): Promise<void> {
  await api.post("/api/v1/auth/logout");
}

export async function refreshApi(): Promise<{ access_token: string }> {
  const { data } = await api.post<{ access_token: string }>("/api/v1/auth/refresh");
  return data;
}
