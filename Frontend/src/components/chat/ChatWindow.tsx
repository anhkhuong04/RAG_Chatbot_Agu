import React, { useEffect, useRef } from "react";
import Message from "../chat/Message";
import type { Message as MessageType } from "../../types/chat";

interface ChatWindowProps {
  messages: MessageType[];
  loading: boolean;
}

const ChatWindow: React.FC<ChatWindowProps> = ({ messages, loading }) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Không hiển thị gì khi chưa có tin nhắn
  if (messages.length === 0) {
    return null;
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 chat-scrollbar bg-white">
      <div className="max-w-4xl mx-auto">
        {messages.map((message) => (
          <Message key={message.id} message={message} />
        ))}

        {loading && (
          <div className="flex items-center gap-3 px-6 py-4 bg-white rounded-2xl w-fit animate-fade-in">
            <div className="flex gap-1">
              <span className="w-2 h-2 bg-orange-400 rounded-full animate-bounce [animation-delay:0ms]"></span>
              <span className="w-2 h-2 bg-orange-400 rounded-full animate-bounce [animation-delay:150ms]"></span>
              <span className="w-2 h-2 bg-orange-400 rounded-full animate-bounce [animation-delay:300ms]"></span>
            </div>
            <span className="text-sm text-gray-600 font-medium">
              Đang suy nghĩ
            </span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
};

export default ChatWindow;
