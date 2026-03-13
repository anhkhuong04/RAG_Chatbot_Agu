import axios from "axios";

// Use relative path for Vite proxy, or full URL for production
const API_BASE_URL = import.meta.env.VITE_API_URL || "";

/**
 * Common Axios Instance for all API calls
 * Sets base URL and default timeout
 */
export const apiClient = axios.create({
    baseURL: API_BASE_URL,
    timeout: 60000, // 60 seconds timeout
    headers: {
        "Content-Type": "application/json",
    },
});

// Configure interceptors if needed (e.g. for Auth tokens)
apiClient.interceptors.request.use(
    (config) => {
        // You can attach tokens here later if implementing auth state
        // const token = useAuthStore.getState().token;
        // if (token) config.headers.Authorization = `Bearer ${token}`;
        return config;
    },
    (error) => Promise.reject(error),
);

apiClient.interceptors.response.use(
    (response) => response,
    (error) => {
        console.error("[API Error]", error?.response?.status, error?.message);
        return Promise.reject(error);
    },
);

export { API_BASE_URL };
