import { useState, useRef, useCallback } from "react";
import {
  sendMessageStream,
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

  // Track the active stream so it can be cancelled
  const abortControllerRef = useRef<AbortController | null>(null);

  const activeConversation = conversations.find(
    (c) => c.id === activeConversationId,
  );

  const createNewConversation = (): string => {
    const newConv: Conversation = {
      id: Date.now().toString(),
      title: "Cuộc trò chuyện mới",
      messages: [],
      timestamp: new Date(),
      serverConversationId: undefined,
    };
    setConversations((prev) => [newConv, ...prev]);
    setActiveConversationId(newConv.id);
    return newConv.id;
  };

  /**
   * Cancel any in-progress stream
   */
  const cancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  const handleSendMessage = async (content: string) => {
    if (!content.trim()) return;

    // Cancel any existing stream
    cancelStream();

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

    // ID cho tin nhắn bot (tạo trước để append tokens)
    const botMessageId = (Date.now() + 1).toString();

    // Placeholder bot message (empty, streaming)
    const botMessage: Message = {
      id: botMessageId,
      content: "",
      role: "assistant",
      timestamp: new Date(),
      isStreaming: true,
    };

    // Thêm tin nhắn user + placeholder bot
    setConversations((prev) =>
      prev.map((conv) =>
        conv.id === convId
          ? {
              ...conv,
              messages: [...conv.messages, userMessage, botMessage],
              title:
                conv.messages.length === 0
                  ? content.slice(0, 30) + "..."
                  : conv.title,
            }
          : conv,
      ),
    );

    setLoading(true);
    setError(null);

    // Capture convId for closures
    const capturedConvId = convId;

    // Get the server conversation ID if exists
    const serverConvId = conversations.find(
      (c) => c.id === capturedConvId,
    )?.serverConversationId;

    console.log("[Stream] Sending message:", content);
    console.log("[Stream] Server conversation ID:", serverConvId || "new");

    const controller = sendMessageStream(content, serverConvId, {
      onToken: (token: string) => {
        // Append token to the bot message content
        setConversations((prev) =>
          prev.map((conv) =>
            conv.id === capturedConvId
              ? {
                  ...conv,
                  messages: conv.messages.map((msg) =>
                    msg.id === botMessageId
                      ? { ...msg, content: msg.content + token }
                      : msg,
                  ),
                }
              : conv,
          ),
        );
      },

      onMetadata: (meta) => {
        console.log("[Stream] Metadata:", meta);
        // Store server session_id for future messages
        if (meta.session_id) {
          setConversations((prev) =>
            prev.map((conv) =>
              conv.id === capturedConvId
                ? { ...conv, serverConversationId: meta.session_id }
                : conv,
            ),
          );
        }
      },

      onSources: (sources) => {
        console.log("[Stream] Sources:", sources);
        // Optionally attach sources to the bot message
        setConversations((prev) =>
          prev.map((conv) =>
            conv.id === capturedConvId
              ? {
                  ...conv,
                  messages: conv.messages.map((msg) =>
                    msg.id === botMessageId
                      ? {
                          ...msg,
                          sources: sources.map((s) => ({
                            content: "",
                            source: s,
                          })),
                        }
                      : msg,
                  ),
                }
              : conv,
          ),
        );
      },

      onDone: () => {
        console.log("[Stream] Complete");
        // Mark streaming as finished
        setConversations((prev) =>
          prev.map((conv) =>
            conv.id === capturedConvId
              ? {
                  ...conv,
                  messages: conv.messages.map((msg) =>
                    msg.id === botMessageId
                      ? { ...msg, isStreaming: false }
                      : msg,
                  ),
                }
              : conv,
          ),
        );
        setLoading(false);
        setError(null);
        abortControllerRef.current = null;
      },

      onError: (err: Error) => {
        console.error("[Stream] Error:", err);
        // Update bot message with error or remove empty placeholder
        setConversations((prev) =>
          prev.map((conv) =>
            conv.id === capturedConvId
              ? {
                  ...conv,
                  messages: conv.messages.map((msg) =>
                    msg.id === botMessageId
                      ? {
                          ...msg,
                          content:
                            msg.content ||
                            "Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại.",
                          isStreaming: false,
                        }
                      : msg,
                  ),
                }
              : conv,
          ),
        );
        setError(err.message);
        setLoading(false);
        abortControllerRef.current = null;
      },
    });

    abortControllerRef.current = controller;
  };

  const selectConversation = (id: string) => {
    setActiveConversationId(id);
    setError(null);
  };

  const deleteConversation = async (id: string) => {
    const conversation = conversations.find((c) => c.id === id);

    if (conversation?.serverConversationId) {
      try {
        await apiDeleteConversation(conversation.serverConversationId);
        console.log(
          "Server conversation deleted:",
          conversation.serverConversationId,
        );
      } catch (err) {
        console.warn("Failed to delete server conversation:", err);
      }
    }

    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (activeConversationId === id) {
      setActiveConversationId(null);
    }
  };

  const renameConversation = (id: string, newTitle: string) => {
    setConversations((prev) =>
      prev.map((conv) =>
        conv.id === id ? { ...conv, title: newTitle } : conv,
      ),
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
    cancelStream,
  };
};
