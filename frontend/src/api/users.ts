import api from "@/lib/axios";

export interface User {
  id: string;
  email: string;
  username: string;
  role: "admin" | "manager" | "viewer";
  is_active: boolean;
  last_login: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserCreatePayload {
  email: string;
  username: string;
  password?: string;
  role: "admin" | "manager" | "viewer";
}

export interface UserUpdatePayload {
  email?: string;
  username?: string;
  role?: "admin" | "manager" | "viewer";
  is_active?: boolean;
  password?: string;
}

export interface PaginatedUsers {
  items: User[];
  total: number;
  page: number;
  page_size: number;
}

export async function listUsers(page: number = 1, pageSize: number = 20): Promise<PaginatedUsers> {
  const { data } = await api.get<PaginatedUsers>("/api/v1/users", {
    params: { page, page_size: pageSize },
  });
  return data;
}

export async function createUser(payload: UserCreatePayload): Promise<User> {
  const { data } = await api.post<User>("/api/v1/users", payload);
  return data;
}

export async function updateUser(userId: string, payload: UserUpdatePayload): Promise<User> {
  const { data } = await api.patch<User>(`/api/v1/users/${userId}`, payload);
  return data;
}

export async function deactivateUser(userId: string): Promise<void> {
  await api.delete(`/api/v1/users/${userId}`);
}
