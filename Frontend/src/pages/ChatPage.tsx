import React from "react";
import { useChatStore } from "../features/chat/store/useChatStore";
import { useChatStream } from "../features/chat/hooks/useChatStream";
import Sidebar from "../features/chat/components/Sidebar";
import ChatWindow from "../features/chat/components/ChatWindow";
import MessageInput from "../features/chat/components/MessageInput";
import "../styles/chat.css";

/**
 * Route: "/chat"
 */
const ChatPage: React.FC = () => {
  const {
    loading,
    error,
    handleSendMessage,
  } = useChatStream();

  const {
    conversations,
    activeConversationId,
    getActiveConversation,
    createNewConversation,
    selectConversation,
    deleteConversation,
    renameConversation,
  } = useChatStore();

  const activeConversation = getActiveConversation();

  const currentYear = new Date().getFullYear();
  const hasMessages = (activeConversation?.messages?.length || 0) > 0;

  // Các gợi ý câu hỏi
  const suggestions = [
    {
      icon: "💡",
      text: "Giới thiệu về Khoa Công nghệ thông tin",
      message: "Giới thiệu về Khoa Công nghệ thông tin",
    },
    {
      icon: "📚",
      text: "Học bổng dành cho tân sinh viên?",
      message: "Học bổng dành cho tân sinh viên?",
    },
    {
      icon: "📊",
      text: "Điểm chuẩn ngành CNTT, KTPM năm trước?",
      message: "Điểm chuẩn các ngành CNTT, KTPM năm trước là bao nhiêu?",
    },
    {
      icon: "💰",
      text: "Học phí dự kiến bao nhiêu cho 1 năm học?",
      message: "Học phí dự kiến bao nhiêu cho 1 năm học ngành CNTT?",
    },
  ];

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-gradient-to-br from-slate-50 via-blue-50 to-purple-50 page-transition">
      {/* Sidebar */}
      <Sidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={selectConversation}
        onNewConversation={createNewConversation}
        onDeleteConversation={deleteConversation}
        onRenameConversation={renameConversation}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        {/* Error Banner */}
        {error && (
          <div className="bg-red-50 border-b border-red-200 px-6 py-3 flex items-center gap-2 z-10">
            <span className="text-red-500">⚠️</span>
            <span className="text-red-700 text-sm flex-1">{error}</span>
          </div>
        )}

        {/* Welcome Screen - Hiển thị khi chưa có tin nhắn */}
        <div
          className={`absolute inset-0 flex flex-col items-center justify-center px-4 bg-white transition-all duration-500 ease-out ${hasMessages
              ? "opacity-0 pointer-events-none scale-95"
              : "opacity-100 pointer-events-auto scale-100"
            }`}
        >
          <div className="text-center mb-8 welcome-content">
            <div className="empty-state-icon text-7xl mb-6">🎓</div>
            <h2 className="text-3xl font-bold bg-gradient-to-r from-yellow-400 to-orange-400 bg-clip-text text-transparent mb-4">
              Xin chào! Tôi là trợ lý ảo tuyển sinh của Khoa Công nghệ Thông tin
              (FIT AGU).
            </h2>
            <p className="text-gray-600 text-lg max-w-xl mx-auto">
              Bạn cần thông tin gì về Trường hay giải đáp thắc mắc về kỳ tuyển
              sinh của Trường Đại học An Giang năm {currentYear}?
            </p>
          </div>

          {/* Input ở giữa màn hình */}
          <div className="w-full max-w-2xl px-4 mb-8">
            <MessageInput
              onSendMessage={handleSendMessage}
              disabled={loading}
              isCentered={true}
              placeholder="Nhập câu hỏi của bạn..."
            />
          </div>

          {/* Các nút gợi ý */}
          <div className="w-full max-w-2xl px-4">
            <div className="grid sm:grid-cols-2 gap-3">
              {suggestions.map((suggestion, index) => (
                <button
                  key={index}
                  className="p-3 bg-white border border-gray-200 rounded-xl text-left text-sm text-gray-700 transition-all duration-200 shadow-sm hover:shadow-md hover:-translate-y-1 hover:border-blue-300"
                  onClick={() => handleSendMessage(suggestion.message)}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{suggestion.icon}</span>
                    <span className="font-medium">{suggestion.text}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Chat Window - Hiển thị khi có tin nhắn */}
        <div
          className={`flex-1 flex flex-col overflow-hidden transition-all duration-500 ease-out ${hasMessages
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-4 pointer-events-none"
            }`}
        >
          <ChatWindow
            messages={activeConversation?.messages || []}
            loading={loading}
          />

          {/* Message Input cố định ở đáy */}
          <div className="bg-white/80 backdrop-blur-sm p-4 flex-shrink-0 border-t border-gray-100 input-container-bottom">
            <MessageInput
              onSendMessage={handleSendMessage}
              disabled={loading}
              isCentered={false}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatPage;
