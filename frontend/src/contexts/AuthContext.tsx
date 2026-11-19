import { AuthContext, type User } from "./useAuth";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { loginApi, logoutApi } from "@/api/auth";
import api, { getAccessToken, setAccessToken } from "@/lib/axios";
import { decodeJwtPayload } from "@/lib/jwt";
import { queryClient } from "@/lib/queryClient";

function userFromToken(token: string, fallbackEmail = ""): User {
  const claims = decodeJwtPayload<{ sub: string; email?: string; full_name?: string; role: string }>(token);
  return { id: claims.sub, email: claims.email ?? fallbackEmail, full_name: claims.full_name ?? "", role: claims.role, is_active: true };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const navigate = useNavigate();

  // Strict Mode replays effects in development. Both runs must share the
  // same refresh request because the server rotates the cookie on use.
  const sessionRequest = useRef<Promise<{ access_token: string }> | null>(null);
  useEffect(() => {
    let active = true;
    sessionRequest.current ??= api.post<{ access_token: string }>("/api/v1/auth/refresh")
      .then(response => response.data);
    sessionRequest.current.then(({ access_token }) => {
      if (!active) return;
      setAccessToken(access_token);
      setUser(userFromToken(access_token));
    }).catch(() => {
      if (!active) return;
      setAccessToken(null);
      setUser(null);
    }).finally(() => {
      if (active) setIsLoading(false);
    });
    return () => { active = false; };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await loginApi(email, password);
    setAccessToken(access_token);
    setUser(userFromToken(access_token, email));
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
