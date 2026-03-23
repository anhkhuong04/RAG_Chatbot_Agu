import { useState, useRef, useCallback } from "react";
import { sendMessageStream } from "../api/chatAPI";
import { useChatStore } from "../store/useChatStore";
import type { Message } from "../../../types/chat";

export const useChatStream = () => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const abortControllerRef = useRef<AbortController | null>(null);

    const {
        activeConversationId,
        getActiveConversation,
        createNewConversation,
        addMessage,
        updateMessage,
        setServerConversationId,
    } = useChatStore();

    const cancelStream = useCallback(() => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
    }, []);

    const handleSendMessage = async (content: string) => {
        if (!content.trim()) return;

        cancelStream();

        let convId = activeConversationId;
        const currentConversation = getActiveConversation();

        if (!convId || !currentConversation) {
            convId = createNewConversation();
        }

        const userMessage: Message = {
            id: Date.now().toString(),
            content,
            role: "user",
            timestamp: new Date(),
        };

        const botMessageId = (Date.now() + 1).toString();
        const botMessage: Message = {
            id: botMessageId,
            content: "",
            role: "assistant",
            timestamp: new Date(),
            isStreaming: true,
        };

        addMessage(convId, userMessage);
        addMessage(convId, botMessage);

        setLoading(true);
        setError(null);

        const capturedConvId = convId;
        // Re-fetch conversation to get latest serverId
        const serverConvId = useChatStore.getState().conversations.find((c) => c.id === capturedConvId)?.serverConversationId;

        const controller = sendMessageStream(content, serverConvId, {
            onToken: (token: string) => {
                // Append token
                const currentMsg = useChatStore.getState().conversations.find((c) => c.id === capturedConvId)?.messages.find(m => m.id === botMessageId);
                if (currentMsg) {
                    updateMessage(capturedConvId, botMessageId, { content: currentMsg.content + token });
                }
            },
            onMetadata: (meta) => {
                if (meta.session_id) {
                    setServerConversationId(capturedConvId, meta.session_id);
                }
            },
            onSources: (sources) => {
                updateMessage(capturedConvId, botMessageId, {
                    sources: sources.map((s) => ({ content: "", source: s })),
                });
            },
            onDone: () => {
                updateMessage(capturedConvId, botMessageId, { isStreaming: false });
                setLoading(false);
                setError(null);
                abortControllerRef.current = null;
            },
            onError: (err: Error) => {
                const currentMsg = useChatStore.getState().conversations.find((c) => c.id === capturedConvId)?.messages.find(m => m.id === botMessageId);
                updateMessage(capturedConvId, botMessageId, {
                    content: currentMsg?.content || "Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại.",
                    isStreaming: false,
                });
                setError(err.message);
                setLoading(false);
                abortControllerRef.current = null;
            },
        });

        abortControllerRef.current = controller;
    };

    const clearError = () => setError(null);

    return {
        loading,
        error,
        handleSendMessage,
        clearError,
        cancelStream,
    };
};
