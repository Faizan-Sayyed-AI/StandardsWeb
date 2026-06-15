import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { loginApi, logoutApi } from "@/api/auth";
import { getAccessToken, setAccessToken } from "@/lib/axios";
import { queryClient } from "@/lib/queryClient";

interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
}

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  isManager: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const navigate = useNavigate();

  // On mount: try to restore session via silent refresh (cookie is present)
  useEffect(() => {
    (async () => {
      try {
        // Attempt silent token refresh using httpOnly cookie
        const { default: api } = await import("@/lib/axios");
        const { data } = await api.post<{ access_token: string }>("/api/v1/auth/refresh");
        setAccessToken(data.access_token);
        // Decode JWT payload to get user info
        const payload = JSON.parse(atob(data.access_token.split(".")[1]));
        setUser({
          id: payload.sub,
          email: payload.email ?? "",
          full_name: payload.full_name ?? "",
          role: payload.role,
          is_active: true,
        });
      } catch {
        setAccessToken(null);
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const data = await loginApi(email, password);
    setAccessToken(data.access_token);
    // Decode payload
    const payload = JSON.parse(atob(data.access_token.split(".")[1]));
    setUser({
      id: payload.sub,
      email: payload.email ?? email,
      full_name: payload.full_name ?? "",
      role: payload.role,
      is_active: true,
    });
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutApi();
    } catch {
      // Ignore errors — clear client state regardless
    }
    setAccessToken(null);
    setUser(null);
    queryClient.clear();
    navigate("/login");
  }, [navigate]);

  const isAdmin = user?.role === "admin";
  const isManager = user?.role === "manager" || isAdmin;

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user && !!getAccessToken(),
        isAdmin,
        isManager,
        login,
        logout,
        isLoading,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
