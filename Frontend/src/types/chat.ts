export interface Message {
  id: string;
  content: string;
  role: "user" | "assistant";
  timestamp: Date;
  sources?: Source[];
  isStreaming?: boolean; // true while tokens are still arriving
}

export interface Source {
  content: string;
  source: string;
  page?: number;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string;
}

export interface ChatResponse {
  response: string;
  sources?: string[];
  conversation_id: string;
}

/** Metadata sent as the first SSE event */
export interface StreamMetadata {
  session_id: string;
  intent: string;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  timestamp: Date;
  serverConversationId?: string; // ID từ server
}

export interface ResetConversationResponse {
  success: boolean;
  message: string;
  conversation_id: string;
}
