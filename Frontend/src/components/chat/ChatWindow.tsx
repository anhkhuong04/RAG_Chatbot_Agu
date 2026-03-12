import React, { useEffect, useRef } from "react";
import Message from "../chat/Message";
import type { Message as MessageType } from "../../types/chat";

interface ChatWindowProps {
  messages: MessageType[];
}

const ChatWindow: React.FC<ChatWindowProps> = ({ messages }) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto scroll to bottom when messages update (including streaming tokens)
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [
    messages,
    messages.length > 0 ? messages[messages.length - 1]?.content : "",
  ]);

  // Không hiển thị gì khi chưa có tin nhắn
  if (messages.length === 0) {
    return null;
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 chat-scrollbar bg-white">
      <div className="max-w-full mx-auto">
        {messages.map((message) => (
          <Message key={message.id} message={message} />
        ))}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
};

export default ChatWindow;
