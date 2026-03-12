import { useState, useEffect, useCallback } from "react";
import type { DocumentItem, UploadFormData } from "../types/admin";
import {
  uploadDocument,
  getDocuments,
  deleteDocument,
  getPrompts,
  updatePrompt,
} from "../services/adminAPI";
import type { PromptItem, PromptUpdatePayload } from "../services/adminAPI";
import { ACADEMIC_YEARS } from "../types/admin";

interface UseAdminReturn {
  // State
  documents: DocumentItem[];
  isLoading: boolean;
  isUploading: boolean;
  error: string | null;
  uploadSuccess: string | null;

  // Prompt state
  prompts: PromptItem[];
  isLoadingPrompts: boolean;
  promptError: string | null;
  promptSuccess: string | null;

  // Actions
  fetchDocuments: () => Promise<void>;
  handleUpload: (formData: UploadFormData) => Promise<boolean>;
  handleDelete: (docUuid: string) => Promise<boolean>;
  clearMessages: () => void;

  // Prompt actions
  fetchPrompts: () => Promise<void>;
  handleUpdatePrompt: (
    intentName: string,
    payload: PromptUpdatePayload,
  ) => Promise<boolean>;
}

export const useAdmin = (): UseAdminReturn => {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);

  // Prompt state
  const [prompts, setPrompts] = useState<PromptItem[]>([]);
  const [isLoadingPrompts, setIsLoadingPrompts] = useState(false);
  const [promptError, setPromptError] = useState<string | null>(null);
  const [promptSuccess, setPromptSuccess] = useState<string | null>(null);

  // Fetch documents from API
  const fetchDocuments = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const docs = await getDocuments();
      setDocuments(docs);
    } catch (err) {
      console.error("Error fetching documents:", err);
      setError("Không thể tải danh sách tài liệu. Vui lòng thử lại.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Upload document
  const handleUpload = useCallback(
    async (formData: UploadFormData): Promise<boolean> => {
      if (!formData.file) {
        setError("Vui lòng chọn file PDF");
        return false;
      }

      setIsUploading(true);
      setError(null);
      setUploadSuccess(null);

      try {
        const result = await uploadDocument(
          formData.file,
          formData.year,
          formData.category,
          formData.description || undefined,
        );

        setUploadSuccess(`Đã upload thành công! ID: ${result.doc_uuid}`);

        // Refresh document list
        await fetchDocuments();

        return true;
      } catch (err: any) {
        console.error("Error uploading document:", err);
        const message =
          err.response?.data?.detail ||
          "Lỗi khi upload file. Vui lòng thử lại.";
        setError(message);
        return false;
      } finally {
        setIsUploading(false);
      }
    },
    [fetchDocuments],
  );

  // Delete document
  const handleDelete = useCallback(
    async (docUuid: string): Promise<boolean> => {
      setError(null);

      try {
        await deleteDocument(docUuid);

        // Remove from local state
        setDocuments((prev) => prev.filter((doc) => doc.doc_uuid !== docUuid));

        return true;
      } catch (err: any) {
        console.error("Error deleting document:", err);
        const message =
          err.response?.data?.detail || "Lỗi khi xóa file. Vui lòng thử lại.";
        setError(message);
        return false;
      }
    },
    [],
  );

  // Clear messages
  const clearMessages = useCallback(() => {
    setError(null);
    setUploadSuccess(null);
    setPromptError(null);
    setPromptSuccess(null);
  }, []);

  // Fetch prompts from API
  const fetchPrompts = useCallback(async () => {
    setIsLoadingPrompts(true);
    setPromptError(null);

    try {
      const data = await getPrompts();
      setPrompts(data);
    } catch (err) {
      console.error("Error fetching prompts:", err);
      setPromptError("Không thể tải danh sách prompts.");
    } finally {
      setIsLoadingPrompts(false);
    }
  }, []);

  // Update a prompt
  const handleUpdatePrompt = useCallback(
    async (
      intentName: string,
      payload: PromptUpdatePayload,
    ): Promise<boolean> => {
      setPromptError(null);
      setPromptSuccess(null);

      try {
        await updatePrompt(intentName, payload);
        setPromptSuccess(`Đã cập nhật prompt "${intentName}" thành công!`);
        // Refresh the list
        await fetchPrompts();
        return true;
      } catch (err) {
        console.error("Error updating prompt:", err);
        setPromptError(`Lỗi khi cập nhật prompt "${intentName}".`);
        return false;
      }
    },
    [fetchPrompts],
  );

  // Initial fetch
  useEffect(() => {
    fetchDocuments();
    fetchPrompts();
  }, [fetchDocuments, fetchPrompts]);

  return {
    documents,
    isLoading,
    isUploading,
    error,
    uploadSuccess,
    prompts,
    isLoadingPrompts,
    promptError,
    promptSuccess,
    fetchDocuments,
    handleUpload,
    handleDelete,
    clearMessages,
    fetchPrompts,
    handleUpdatePrompt,
  };
};

// Default form values
export const getDefaultFormData = (): UploadFormData => ({
  file: null,
  year: ACADEMIC_YEARS[0],
  category: "",
  description: "",
});
