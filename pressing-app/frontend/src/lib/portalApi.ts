import axios from "axios";

export const portalApi = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
});

portalApi.interceptors.request.use((config) => {
  const token = localStorage.getItem("pressing_portal_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

portalApi.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401 && !window.location.pathname.startsWith("/portal/login")) {
      localStorage.removeItem("pressing_portal_token");
      localStorage.removeItem("pressing_portal_customer");
      window.location.href = "/portal/login";
    }
    return Promise.reject(error);
  }
);
