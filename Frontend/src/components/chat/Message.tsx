import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { User, Bot } from "lucide-react";
import type { Message as MessageType } from "../../types/chat";

interface MessageProps {
  message: MessageType;
}

const Message: React.FC<MessageProps> = ({ message }) => {
  const isUser = message.role === "user";

  return (
    <div
      className={`message-animate flex gap-4 mb-8 ${
        isUser ? "flex-row-reverse justify-start" : "justify-start"
      }`}
    >
      {/* Avatar */}
      <div className="flex-shrink-0">
        {isUser ? (
          <div className="w-10 h-10 rounded-full bg-blue-600 text-white flex items-center justify-center shadow-lg ring-2 ring-blue-100">
            <User size={20} />
          </div>
        ) : (
          <div className="w-10 h-10 rounded-full bg-orange-400 text-white flex items-center justify-center shadow-lg ring-2 ring-purple-100">
            <Bot size={20} />
          </div>
        )}
      </div>

      {/* Message Content */}
      <div
        className={`min-w-0 ${isUser ? "max-w-[70%]" : "flex-1 max-w-[85%]"}`}
      >
        {/* Header */}
        <div
          className={`flex items-center gap-2 mb-2 ${
            isUser ? "justify-end" : ""
          }`}
        >
          <span
            className={`text-sm font-bold ${
              isUser ? "text-gray-700" : "gradient-text-bot"
            }`}
          >
            {isUser ? "Bạn" : "AGU Tư Vấn"}
          </span>
          <span className="text-xs text-gray-400 font-medium">
            {message.timestamp.toLocaleTimeString("vi-VN", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </div>

        {/* Message Text */}
        <div
          className={`rounded-2xl px-5 py-3.5 ${
            isUser
              ? "bg-gradient-to-br from-blue-600 to-blue-700 text-white message-user-bubble"
              : "bg-white text-gray-800 border border-gray-100 message-bot-bubble"
          }`}
        >
          {isUser ? (
            <p className="text-[15px] leading-relaxed font-medium">
              {message.content}
            </p>
          ) : (
            <div className="markdown-content prose prose-sm max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Message;
