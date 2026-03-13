import axios, { AxiosError } from "axios";
import type {
  ChatResponse,
  ChatRequest,
  ResetConversationResponse,
  StreamMetadata,
} from "../../../types/chat";

// Use relative path for Vite proxy, or full URL for production
const API_BASE_URL = import.meta.env.VITE_API_URL || "";

// Configure axios defaults
axios.defaults.timeout = 60000; // 60 seconds timeout
axios.defaults.headers.post["Content-Type"] = "application/json";

// ============================================
// SSE STREAMING CALLBACKS
// ============================================

export interface StreamCallbacks {
  /** Called with each text token as it arrives */
  onToken: (token: string) => void;
  /** Called once when metadata (session_id, intent) is received */
  onMetadata?: (meta: StreamMetadata) => void;
  /** Called once when sources are available (RAG queries) */
  onSources?: (sources: string[]) => void;
  /** Called when the stream is fully complete */
  onDone: () => void;
  /** Called if an error occurs during streaming */
  onError: (error: Error) => void;
}

/**
 * Send a chat message and stream the response via SSE.
 * Uses the native fetch API + ReadableStream to process events.
 *
 * @param message - The user's message
 * @param conversationId - Optional session ID for continuity
 * @param callbacks - Handlers for stream events
 * @returns An AbortController so the caller can cancel the stream
 */
export const sendMessageStream = (
  message: string,
  conversationId: string | undefined,
  callbacks: StreamCallbacks,
): AbortController => {
  const controller = new AbortController();
  const endpoint = `${API_BASE_URL}/api/v1/chat/stream`;

  const body: ChatRequest = {
    message: message.trim(),
    conversation_id: conversationId,
  };

  // Run the async streaming logic
  (async () => {
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(
          `HTTP ${response.status}: ${errorText || "Lỗi kết nối server"}`,
        );
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error(
          "ReadableStream không được hỗ trợ trên trình duyệt này.",
        );
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE lines from buffer
        const lines = buffer.split("\n");
        // Keep the last (possibly incomplete) line in the buffer
        buffer = lines.pop() || "";

        let currentEvent = "";
        let dataLines: string[] = [];

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            // If we had a previous event with data, process it first
            if (currentEvent && dataLines.length > 0) {
              processSSEEvent(currentEvent, dataLines.join("\n"), callbacks);
            }
            currentEvent = line.slice(7).trim();
            dataLines = [];
          } else if (line.startsWith("data: ")) {
            dataLines.push(line.slice(6));
          } else if (line === "" && currentEvent && dataLines.length > 0) {
            // Empty line = end of event
            processSSEEvent(currentEvent, dataLines.join("\n"), callbacks);
            currentEvent = "";
            dataLines = [];
          }
        }

        // Process any remaining event in progress
        if (currentEvent && dataLines.length > 0) {
          processSSEEvent(currentEvent, dataLines.join("\n"), callbacks);
          currentEvent = "";
          dataLines = [];
        }
      }

      // Process any remaining buffer
      if (buffer.trim()) {
        const remaining = buffer.split("\n");
        let currentEvent = "";
        let dataLines: string[] = [];
        for (const line of remaining) {
          if (line.startsWith("event: ")) {
            if (currentEvent && dataLines.length > 0) {
              processSSEEvent(currentEvent, dataLines.join("\n"), callbacks);
            }
            currentEvent = line.slice(7).trim();
            dataLines = [];
          } else if (line.startsWith("data: ")) {
            dataLines.push(line.slice(6));
          }
        }
        if (currentEvent && dataLines.length > 0) {
          processSSEEvent(currentEvent, dataLines.join("\n"), callbacks);
        }
      }

      callbacks.onDone();
    } catch (err: unknown) {
      // Ignore abort errors (user cancelled)
      if (err instanceof DOMException && err.name === "AbortError") {
        callbacks.onDone();
        return;
      }

      const error =
        err instanceof Error
          ? err
          : new Error("Đã xảy ra lỗi không xác định khi streaming.");

      console.error("[Stream Error]", error);
      callbacks.onError(error);
    }
  })();

  return controller;
};

/** Parse a single SSE event and call the appropriate callback */
function processSSEEvent(
  event: string,
  data: string,
  callbacks: StreamCallbacks,
) {
  switch (event) {
    case "token":
      callbacks.onToken(data);
      break;
    case "metadata":
      try {
        const meta: StreamMetadata = JSON.parse(data);
        callbacks.onMetadata?.(meta);
      } catch {
        console.warn("Failed to parse metadata:", data);
      }
      break;
    case "sources":
      try {
        const sources: string[] = JSON.parse(data);
        callbacks.onSources?.(sources);
      } catch {
        console.warn("Failed to parse sources:", data);
      }
      break;
    case "done":
      // Will be handled by the reader loop ending
      break;
    case "error":
      try {
        const errData = JSON.parse(data);
        callbacks.onError(new Error(errData.error || "Stream error"));
      } catch {
        callbacks.onError(new Error(data));
      }
      break;
    default:
      console.warn("Unknown SSE event:", event, data);
  }
}

// ============================================
// LEGACY NON-STREAMING API (kept for fallback)
// ============================================

/**
 * Send a chat message to the server (non-streaming fallback)
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
        `Lỗi HTTP ${status}: ${errorData?.detail?.message || errorData?.detail || axiosError.message
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
