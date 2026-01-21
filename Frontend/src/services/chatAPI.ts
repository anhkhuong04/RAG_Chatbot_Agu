import axios, { AxiosError } from "axios";
import type {
  ChatResponse,
  ChatRequest,
  ResetConversationResponse,
} from "../types/chat";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Configure axios defaults
axios.defaults.timeout = 60000; // 60 seconds timeout
axios.defaults.headers.post["Content-Type"] = "application/json";

/**
 * Send a chat message to the server
 * @param message - The user's message
 * @param conversationId - Optional conversation ID to continue existing conversation
 * @returns ChatResponse with response text, sources, and conversation_id
 */
export const sendMessage = async (
  message: string,
  conversationId?: string,
): Promise<ChatResponse> => {
  // Validate input
  if (!message || !message.trim()) {
    throw new Error("Tin nhắn không được để trống");
  }

  const endpoint = `${API_BASE_URL}/api/v1/chat`;
  console.log(`Sending request to: ${endpoint}`);
  console.log(`Message: ${message.substring(0, 50)}...`);
  if (conversationId) {
    console.log(`Conversation ID: ${conversationId}`);
  }

  try {
    const requestBody: ChatRequest = {
      message: message.trim(),
      conversation_id: conversationId,
    };

    const response = await axios.post(endpoint, requestBody);

    console.log("Response received:", response.status);
    console.log("Data:", response.data);

    // Validate response structure
    if (!response.data || typeof response.data.response !== "string") {
      throw new Error("Invalid response format from server");
    }

    // Return response with conversation_id
    return {
      response: response.data.response,
      sources: response.data.sources || [],
      conversation_id: response.data.conversation_id,
    };
  } catch (error) {
    console.error("API Error:", error);

    // Handle specific error types
    if (axios.isAxiosError(error)) {
      const axiosError = error as AxiosError;

      // Network error
      if (!axiosError.response) {
        if (axiosError.code === "ECONNREFUSED") {
          throw new Error(
            "Không thể kết nối tới server. Vui lòng kiểm tra backend đang chạy tại " +
              API_BASE_URL,
          );
        }
        if (
          axiosError.code === "ETIMEDOUT" ||
          axiosError.message.includes("timeout")
        ) {
          throw new Error(
            "Request timeout. Server mất quá nhiều thời gian để trả lời.",
          );
        }
        throw new Error("Lỗi kết nối. Vui lòng kiểm tra internet và thử lại.");
      }

      // Server error with response
      const status = axiosError.response.status;
      const errorData = axiosError.response.data as any;

      if (status === 500) {
        const errorMsg =
          errorData?.detail?.message || errorData?.detail || "Lỗi server";
        throw new Error(`Lỗi server: ${errorMsg}`);
      }

      if (status === 400) {
        const errorMsg = errorData?.detail?.message || "Dữ liệu không hợp lệ";
        throw new Error(errorMsg);
      }

      if (status === 422) {
        throw new Error("Dữ liệu không hợp lệ. Vui lòng kiểm tra tin nhắn.");
      }

      if (status === 404) {
        throw new Error(
          `Endpoint không tồn tại: ${endpoint}. Vui lòng kiểm tra cấu hình.`,
        );
      }

      throw new Error(
        `Lỗi HTTP ${status}: ${
          errorData?.detail?.message || errorData?.detail || axiosError.message
        }`,
      );
    }

    // Generic error
    throw new Error(
      error instanceof Error ? error.message : "Đã xảy ra lỗi không xác định",
    );
  }
};

/**
 * Reset a conversation's chat history
 * @param conversationId - The conversation ID to reset
 */
export const resetConversation = async (
  conversationId: string,
): Promise<ResetConversationResponse> => {
  const endpoint = `${API_BASE_URL}/api/v1/chat/reset`;

  try {
    const response = await axios.post(endpoint, {
      conversation_id: conversationId,
    });

    return response.data;
  } catch (error) {
    console.error("Reset conversation failed:", error);
    throw error;
  }
};

/**
 * Delete a conversation
 * @param conversationId - The conversation ID to delete
 */
export const deleteConversation = async (
  conversationId: string,
): Promise<ResetConversationResponse> => {
  const endpoint = `${API_BASE_URL}/api/v1/chat/${conversationId}`;

  try {
    const response = await axios.delete(endpoint);
    return response.data;
  } catch (error) {
    console.error("Delete conversation failed:", error);
    throw error;
  }
};
