import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

const TOKEN_KEY = "admin_token";

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export const login = async (
  username: string,
  password: string,
): Promise<LoginResponse> => {
  const response = await axios.post<LoginResponse>(
    `${API_BASE_URL}/api/v1/admin/login`,
    { username, password },
  );
  return response.data;
};

export const getToken = (): string | null => {
  return localStorage.getItem(TOKEN_KEY);
};

export const setToken = (token: string): void => {
  localStorage.setItem(TOKEN_KEY, token);
};

export const removeToken = (): void => {
  localStorage.removeItem(TOKEN_KEY);
};
