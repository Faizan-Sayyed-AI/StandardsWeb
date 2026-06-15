import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// In-memory access token store (not localStorage — XSS protection)
let _accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  _accessToken = token;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true, // send httpOnly refresh_token cookie on all requests
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor: attach access token to every request
api.interceptors.request.use((config) => {
  if (_accessToken) {
    config.headers.Authorization = `Bearer ${_accessToken}`;
  }
  return config;
});

// Response interceptor: transparently refresh on 401
let _refreshing = false;
let _refreshQueue: Array<(token: string) => void> = [];

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;

    // Only attempt refresh on 401, and avoid infinite loops
    if (
      error.response?.status === 401 &&
      !original._retried &&
      !original.url?.includes("/auth/refresh") &&
      !original.url?.includes("/auth/login")
    ) {
      original._retried = true;

      if (_refreshing) {
        // Queue this request until the refresh resolves
        return new Promise((resolve) => {
          _refreshQueue.push((token) => {
            original.headers.Authorization = `Bearer ${token}`;
            resolve(api(original));
          });
        });
      }

      _refreshing = true;
      try {
        const { data } = await api.post<{ access_token: string }>("/api/v1/auth/refresh");
        const newToken = data.access_token;
        setAccessToken(newToken);
        _refreshQueue.forEach((cb) => cb(newToken));
        _refreshQueue = [];
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      } catch {
        // Refresh failed — clear token and redirect to login
        setAccessToken(null);
        window.location.href = "/login";
        return Promise.reject(error);
      } finally {
        _refreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default api;
