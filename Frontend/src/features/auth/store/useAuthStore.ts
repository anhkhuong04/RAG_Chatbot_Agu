import { create } from "zustand";
import { persist } from "zustand/middleware";
import { loginAPI } from "../api/authAPI";

interface AuthState {
    token: string | null;
    isAuthenticated: boolean;
    isLoggingIn: boolean;
    loginError: string | null;

    login: (username: string, password: string) => Promise<boolean>;
    logout: () => void;
    clearError: () => void;
}

export const useAuthStore = create<AuthState>()(
    persist(
        (set) => ({
            token: null,
            isAuthenticated: false,
            isLoggingIn: false,
            loginError: null,

            login: async (username, password) => {
                set({ isLoggingIn: true, loginError: null });
                try {
                    const data = await loginAPI(username, password);
                    set({
                        token: data.access_token,
                        isAuthenticated: true,
                        isLoggingIn: false,
                    });
                    return true;
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                } catch (err: any) {
                    const message =
                        err.response?.data?.detail || "Đăng nhập thất bại. Vui lòng thử lại.";
                    set({ loginError: message, isLoggingIn: false });
                    return false;
                }
            },

            logout: () => {
                set({ token: null, isAuthenticated: false, loginError: null });
            },

            clearError: () => set({ loginError: null }),
        }),
        {
            name: "admin_auth_storage",
            partialize: (state) => ({ token: state.token, isAuthenticated: state.isAuthenticated }),
        },
    ),
);
