import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Conversation, Message } from "../../../types/chat";
import { deleteConversation as apiDeleteConversation } from "../api/chatAPI";

interface ChatState {
    conversations: Conversation[];
    activeConversationId: string | null;

    // Actions
    createNewConversation: () => string;
    selectConversation: (id: string) => void;
    deleteConversation: (id: string) => Promise<void>;
    renameConversation: (id: string, newTitle: string) => void;

    // Message mutations
    addMessage: (convId: string, message: Message) => void;
    updateMessage: (convId: string, messageId: string, updates: Partial<Message>) => void;
    setServerConversationId: (convId: string, serverId: string) => void;

    // Gets active conversation
    getActiveConversation: () => Conversation | undefined;
}

export const useChatStore = create<ChatState>()(
    persist(
        (set, get) => ({
            conversations: [],
            activeConversationId: null,

            getActiveConversation: () => {
                const { conversations, activeConversationId } = get();
                return conversations.find((c) => c.id === activeConversationId);
            },

            createNewConversation: () => {
                const newConv: Conversation = {
                    id: Date.now().toString(),
                    title: "Cuộc trò chuyện mới",
                    messages: [],
                    timestamp: new Date(),
                    serverConversationId: undefined,
                };
                set((state) => ({
                    conversations: [newConv, ...state.conversations],
                    activeConversationId: newConv.id,
                }));
                return newConv.id;
            },

            selectConversation: (id: string) => {
                set({ activeConversationId: id });
            },

            deleteConversation: async (id: string) => {
                const { conversations } = get();
                const conversation = conversations.find((c) => c.id === id);

                if (conversation?.serverConversationId) {
                    try {
                        await apiDeleteConversation(conversation.serverConversationId);
                    } catch (err) {
                        console.warn("Failed to delete server conversation:", err);
                    }
                }

                set((state) => ({
                    conversations: state.conversations.filter((c) => c.id !== id),
                    activeConversationId:
                        state.activeConversationId === id ? null : state.activeConversationId,
                }));
            },

            renameConversation: (id: string, newTitle: string) => {
                set((state) => ({
                    conversations: state.conversations.map((conv) =>
                        conv.id === id ? { ...conv, title: newTitle } : conv
                    ),
                }));
            },

            addMessage: (convId: string, message: Message) => {
                set((state) => ({
                    conversations: state.conversations.map((conv) =>
                        conv.id === convId
                            ? {
                                ...conv,
                                messages: [...conv.messages, message],
                                title:
                                    conv.messages.length === 0
                                        ? message.content.slice(0, 30) + "..."
                                        : conv.title,
                            }
                            : conv
                    ),
                }));
            },

            updateMessage: (convId: string, messageId: string, updates: Partial<Message>) => {
                set((state) => ({
                    conversations: state.conversations.map((conv) =>
                        conv.id === convId
                            ? {
                                ...conv,
                                messages: conv.messages.map((msg) =>
                                    msg.id === messageId ? { ...msg, ...updates } : msg
                                ),
                            }
                            : conv
                    ),
                }));
            },

            setServerConversationId: (convId: string, serverId: string) => {
                set((state) => ({
                    conversations: state.conversations.map((conv) =>
                        conv.id === convId
                            ? { ...conv, serverConversationId: serverId }
                            : conv
                    ),
                }));
            },
        }),
        {
            name: "agu_chat_conversations",
            partialize: (state) => ({
                conversations: state.conversations,
                activeConversationId: state.activeConversationId,
            }),
            // Deserialize dates correctly and strip transient state
            merge: (persistedState: any, currentState) => {
                if (!persistedState || !persistedState.conversations) return currentState;

                return {
                    ...currentState,
                    activeConversationId: persistedState.activeConversationId,
                    conversations: persistedState.conversations.map((conv: any) => ({
                        ...conv,
                        timestamp: new Date(conv.timestamp),
                        messages: conv.messages.map((msg: any) => ({
                            ...msg,
                            timestamp: new Date(msg.timestamp),
                            isStreaming: false, // Never persist streaming state
                        })),
                    })),
                };
            },
        }
    )
);
