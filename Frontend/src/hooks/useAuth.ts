import { useState, useCallback, useEffect } from "react";
import {
  login as apiLogin,
  getToken,
  setToken,
  removeToken,
} from "../services/authService";

interface UseAuthReturn {
  isAuthenticated: boolean;
  isLoggingIn: boolean;
  loginError: string | null;
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => void;
}

export const useAuth = (): UseAuthReturn => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(!!getToken());
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  // Sync state if token is removed externally
  useEffect(() => {
    setIsAuthenticated(!!getToken());
  }, []);

  const login = useCallback(
    async (username: string, password: string): Promise<boolean> => {
      setIsLoggingIn(true);
      setLoginError(null);

      try {
        const data = await apiLogin(username, password);
        setToken(data.access_token);
        setIsAuthenticated(true);
        return true;
      } catch (err: any) {
        const message =
          err.response?.data?.detail || "Đăng nhập thất bại. Vui lòng thử lại.";
        setLoginError(message);
        return false;
      } finally {
        setIsLoggingIn(false);
      }
    },
    [],
  );

  const logout = useCallback(() => {
    removeToken();
    setIsAuthenticated(false);
  }, []);

  return { isAuthenticated, isLoggingIn, loginError, login, logout };
};
