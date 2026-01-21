import { useState } from "react";
import {
  sendMessage,
  deleteConversation as apiDeleteConversation,
} from "../services/chatAPI";
import type { Message, Conversation } from "../types/chat";

export const useChat = () => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeConversation = conversations.find(
    (c) => c.id === activeConversationId
  );

  const createNewConversation = (): string => {
    const newConv: Conversation = {
      id: Date.now().toString(),
      title: "Cuộc trò chuyện mới",
      messages: [],
      timestamp: new Date(),
      serverConversationId: undefined, // Will be set after first message
    };
    setConversations((prev) => [newConv, ...prev]);
    setActiveConversationId(newConv.id);
    return newConv.id;
  };

  const handleSendMessage = async (content: string) => {
    if (!content.trim()) return;

    let convId = activeConversationId;
    let currentConversation = activeConversation;

    // Tạo conversation mới nếu chưa có
    if (!convId || !currentConversation) {
      convId = createNewConversation();
      currentConversation = {
        id: convId,
        title: "Cuộc trò chuyện mới",
        messages: [],
        timestamp: new Date(),
      };
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      content,
      role: "user",
      timestamp: new Date(),
    };

    // Thêm tin nhắn user
    setConversations((prev) =>
      prev.map((conv) =>
        conv.id === convId
          ? {
              ...conv,
              messages: [...conv.messages, userMessage],
              title:
                conv.messages.length === 0
                  ? content.slice(0, 30) + "..."
                  : conv.title,
            }
          : conv
      )
    );

    setLoading(true);
    setError(null);

    try {
      // Get the server conversation ID if exists
      const serverConvId = conversations.find(
        (c) => c.id === convId
      )?.serverConversationId;

      console.log("Sending message:", content);
      console.log(
        "Server conversation ID:",
        serverConvId || "new conversation"
      );

      // Send message with conversation_id for session continuity
      const response = await sendMessage(content, serverConvId);
      console.log("Response received:", response);

      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: response.response,
        role: "assistant",
        timestamp: new Date(),
      };

      // Update conversation with bot message and server conversation ID
      setConversations((prev) =>
        prev.map((conv) =>
          conv.id === convId
            ? {
                ...conv,
                messages: [...conv.messages, botMessage],
                // Store the server's conversation_id for future messages
                serverConversationId: response.conversation_id,
              }
            : conv
        )
      );

      // Clear error on success
      setError(null);
    } catch (err) {
      // Use error message from chatAPI if available
      const errorMessage =
        err instanceof Error
          ? err.message
          : "Không thể gửi tin nhắn. Vui lòng thử lại.";

      setError(errorMessage);
      console.error("Error:", err);
    } finally {
      setLoading(false);
    }
  };

  const selectConversation = (id: string) => {
    setActiveConversationId(id);
    setError(null); // Clear error when switching conversations
  };

  const deleteConversation = async (id: string) => {
    const conversation = conversations.find((c) => c.id === id);

    // Try to delete from server if we have a server conversation ID
    if (conversation?.serverConversationId) {
      try {
        await apiDeleteConversation(conversation.serverConversationId);
        console.log(
          "Server conversation deleted:",
          conversation.serverConversationId
        );
      } catch (err) {
        console.warn("Failed to delete server conversation:", err);
        // Continue with local deletion even if server deletion fails
      }
    }

    // Delete locally
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (activeConversationId === id) {
      setActiveConversationId(null);
    }
  };

  const renameConversation = (id: string, newTitle: string) => {
    setConversations((prev) =>
      prev.map((conv) => (conv.id === id ? { ...conv, title: newTitle } : conv))
    );
  };

  const clearError = () => {
    setError(null);
  };

  return {
    conversations,
    activeConversation,
    activeConversationId,
    loading,
    error,
    handleSendMessage,
    createNewConversation,
    selectConversation,
    deleteConversation,
    renameConversation,
    clearError,
  };
};
