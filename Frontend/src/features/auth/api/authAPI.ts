import { apiClient } from "../../../lib/api";

export interface LoginResponse {
    access_token: string;
    token_type: string;
}

/**
 * Login API Call
 */
export const loginAPI = async (
    username: string,
    password: string,
): Promise<LoginResponse> => {
    const response = await apiClient.post<LoginResponse>(
        "/api/v1/admin/login",
        { username, password },
    );
    return response.data;
};
