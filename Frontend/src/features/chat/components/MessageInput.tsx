import React, { useState, type KeyboardEvent, useRef, useEffect } from "react";
import { Send } from "lucide-react";

interface MessageInputProps {
  onSendMessage: (message: string) => void;
  disabled: boolean;
  isCentered?: boolean;
  placeholder?: string;
}

const MessageInput: React.FC<MessageInputProps> = ({
  onSendMessage,
  disabled,
  isCentered = false,
  placeholder = "Nhập câu hỏi của bạn...",
}) => {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    if (input.trim() && !disabled) {
      onSendMessage(input);
      setInput("");
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = e.target.scrollHeight + "px";
  };

  // Auto focus when centered (welcome screen)
  useEffect(() => {
    if (isCentered && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [isCentered]);

  return (
    <div
      className={`w-full transition-all duration-500 ease-out ${
        isCentered ? "max-w-2xl" : "max-w-4xl"
      } mx-auto`}
    >
      <div
        className={`flex items-end gap-3 bg-white rounded-2xl p-4 border-2 border-gray-200 input-focus-glow transition-all duration-300 ${
          isCentered ? "shadow-xl" : "shadow-md"
        }`}
      >
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className="textarea-smooth flex-1 bg-transparent border-none outline-none resize-none text-gray-900 placeholder-gray-400 text-[15px] max-h-32 disabled:opacity-50 leading-relaxed"
        />

        <button
          onClick={handleSend}
          disabled={disabled || !input.trim()}
          className="p-3 bg-blue-600 text-white rounded-xl border-none cursor-pointer transition-all duration-300 flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:from-blue-600 shadow-lg hover:shadow-xl transform hover:scale-105 disabled:transform-none"
          title="Gửi tin nhắn"
        >
          <Send size={20} />
        </button>
      </div>
    </div>
  );
};

export default MessageInput;
