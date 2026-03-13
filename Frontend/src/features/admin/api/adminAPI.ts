import axios from "axios";
import type { DocumentItem, UploadResponse } from "../../../types/admin";
import { useAuthStore } from "../../auth/store/useAuthStore";

// Use relative path when proxied, or full URL for production
const API_BASE_URL = import.meta.env.VITE_API_URL || "";

// Axios instance with auth interceptor
const adminAxios = axios.create();

adminAxios.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

adminAxios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && useAuthStore.getState().token) {
      useAuthStore.getState().logout();
      window.location.reload();
    }
    return Promise.reject(error);
  },
);

/**
 * Admin API Service
 * Handles all admin-related API calls for knowledge base management
 */

// ============================================
// PROMPT TYPES
// ============================================

export interface PromptItem {
  intent_name: string;
  system_prompt: string;
  user_template: string;
  description: string;
  is_active: boolean;
  updated_at: string;
  created_at: string;
}

export interface PromptUpdatePayload {
  system_prompt?: string;
  user_template?: string;
  description?: string;
  is_active?: boolean;
}

// ============================================
// DOCUMENT API
// ============================================

/**
 * Upload a PDF document to the knowledge base
 */
export const uploadDocument = async (
  file: File,
  year: number,
  category: string,
  description?: string,
): Promise<UploadResponse> => {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("year", year.toString());
  formData.append("category", category);
  if (description) {
    formData.append("description", description);
  }

  const response = await adminAxios.post<UploadResponse>(
    `${API_BASE_URL}/api/v1/admin/upload`,
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
      timeout: 120000, // 2 minutes for large files
    },
  );

  return response.data;
};

/**
 * Get list of all documents in the knowledge base
 */
export const getDocuments = async (): Promise<DocumentItem[]> => {
  const response = await adminAxios.get<DocumentItem[]>(
    `${API_BASE_URL}/api/v1/admin/documents`,
  );
  return response.data;
};

/**
 * Delete a document from the knowledge base
 */
export const deleteDocument = async (docUuid: string): Promise<void> => {
  await adminAxios.delete(`${API_BASE_URL}/api/v1/admin/documents/${docUuid}`);
};

// ============================================
// PROMPT MANAGEMENT API
// ============================================

/**
 * Get list of all intent prompts
 */
export const getPrompts = async (): Promise<PromptItem[]> => {
  const response = await adminAxios.get<PromptItem[]>(
    `${API_BASE_URL}/api/v1/admin/prompts`,
  );
  return response.data;
};

/**
 * Get a single prompt by intent name
 */
export const getPrompt = async (intentName: string): Promise<PromptItem> => {
  const response = await adminAxios.get<PromptItem>(
    `${API_BASE_URL}/api/v1/admin/prompts/${intentName}`,
  );
  return response.data;
};

/**
 * Update a prompt's content
 */
export const updatePrompt = async (
  intentName: string,
  payload: PromptUpdatePayload,
): Promise<PromptItem> => {
  const response = await adminAxios.put<PromptItem>(
    `${API_BASE_URL}/api/v1/admin/prompts/${intentName}`,
    payload,
  );
  return response.data;
};
