import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  MessageSquarePlus,
  Trash2,
  MoreVertical,
  Edit2,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import ConfirmDialog from "./ConfirmDialog";
import PromptDialog from "./PromptDialog";

interface Conversation {
  id: string;
  title: string;
  timestamp: Date;
}

interface SidebarProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewConversation: () => void;
  onDeleteConversation: (id: string) => void;
  onRenameConversation: (id: string, newTitle: string) => void;
}

const Sidebar: React.FC<SidebarProps> = ({
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  onRenameConversation,
}) => {
  const navigate = useNavigate();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [deleteDialog, setDeleteDialog] = useState<{
    isOpen: boolean;
    convId: string;
    title: string;
  }>({ isOpen: false, convId: "", title: "" });
  const [renameDialog, setRenameDialog] = useState<{
    isOpen: boolean;
    convId: string;
    currentTitle: string;
  }>({ isOpen: false, convId: "", currentTitle: "" });

  const handleDelete = (e: React.MouseEvent, convId: string, title: string) => {
    e.stopPropagation();
    setOpenMenuId(null);
    setDeleteDialog({ isOpen: true, convId, title });
  };

  const confirmDelete = () => {
    onDeleteConversation(deleteDialog.convId);
    setDeleteDialog({ isOpen: false, convId: "", title: "" });
  };

  const cancelDelete = () => {
    setDeleteDialog({ isOpen: false, convId: "", title: "" });
  };

  const handleRename = (
    e: React.MouseEvent,
    convId: string,
    currentTitle: string,
  ) => {
    e.stopPropagation();
    setOpenMenuId(null);
    setRenameDialog({ isOpen: true, convId, currentTitle });
  };

  const confirmRename = (newTitle: string) => {
    if (newTitle && newTitle !== renameDialog.currentTitle) {
      onRenameConversation(renameDialog.convId, newTitle);
    }
    setRenameDialog({ isOpen: false, convId: "", currentTitle: "" });
  };

  const cancelRename = () => {
    setRenameDialog({ isOpen: false, convId: "", currentTitle: "" });
  };

  const toggleMenu = (e: React.MouseEvent, convId: string) => {
    e.stopPropagation();
    setOpenMenuId(openMenuId === convId ? null : convId);
  };

  const handleMain = () => {
    navigate("/");
  };
  return (
    <div
      className={`${isCollapsed ? "w-[70px] min-w-[70px]" : "w-[280px] min-w-[280px]"} bg-gray-100 text-gray-900 flex flex-col shadow-xl transition-all duration-300`}
    >
      {/* Logo Section */}
      {!isCollapsed && (
        <div className="flex justify-center items-center pt-6 pb-4 bg-gradient-to-b from-gray-50 to-gray-100">
          <img
            src="images/logo_agu.png"
            alt="AGU Logo"
            className="w-48 h-24 object-contain drop-shadow-lg"
            onClick={handleMain}
          />
        </div>
      )}

      {/* Title Section */}
      {!isCollapsed && (
        <div className="px-4 pb-4">
          <h3 className="text-xl font-extrabold bg-orange-400 bg-clip-text text-transparent text-center m-0 leading-tight">
            AGU Tư Vấn Tuyển Sinh
          </h3>
          <p className="text-sm text-black text-center mt-2 font-medium">
            Trợ lý ảo hỗ trợ tư vấn tuyển sinh Trường Đại học An Giang
          </p>
        </div>
      )}

      {/* New Chat Button with pulse effect */}
      <button
        className={`mx-auto mt-2 mb-4 ${isCollapsed ? "p-3 rounded-full w-12 h-12" : "mx-4 px-5 py-3.5 rounded-xl"} bg-blue-600 border-none text-white text-base font-bold flex items-center justify-center gap-3 cursor-pointer transition-all duration-300 flex-shrink-0 shadow-lg hover:shadow-xl transform hover:scale-[1.02] new-chat-pulse`}
        onClick={onNewConversation}
        title={isCollapsed ? "Cuộc trò chuyện mới" : ""}
      >
        <MessageSquarePlus size={isCollapsed ? 20 : 22} />
        {!isCollapsed && <span>Cuộc trò chuyện mới</span>}
      </button>

      {/* Conversations List */}
      {!isCollapsed && (
        <div className="flex-1 overflow-y-auto overflow-x-visible px-4 pb-4 chat-scrollbar bg-gray-100">
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-600 font-semibold text-sm">
              {conversations.length} cuộc trò chuyện
            </span>
          </div>
          {conversations.length === 0 ? (
            <div className="text-center mt-40 empty-state-icon">
              <p className="text-gray-900 text-sm">
                Chưa có cuộc trò chuyện nào
              </p>
            </div>
          ) : (
            conversations.map((conv, index) => (
              <div
                key={conv.id}
                className={`group relative p-3 mb-2 rounded-xl cursor-pointer flex items-center justify-between transition-all duration-300 ${
                  activeConversationId === conv.id
                    ? "bg-blue-100 border border-blue-300 shadow-sm"
                    : "bg-white border border-transparent hover:bg-gray-50 hover:border-gray-200"
                }`}
                onClick={() => onSelectConversation(conv.id)}
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="block text-sm font-semibold text-gray-900 whitespace-nowrap overflow-hidden text-ellipsis">
                      {conv.title}
                    </span>
                  </div>
                </div>

                <div className="relative flex items-center">
                  <button
                    className={`p-1.5 bg-transparent border-none text-gray-400 cursor-pointer transition-all duration-200 flex items-center rounded-lg hover:bg-white hover:text-gray-900 hover:shadow-sm ${
                      openMenuId === conv.id
                        ? "opacity-100"
                        : "opacity-0 group-hover:opacity-100"
                    }`}
                    onClick={(e) => toggleMenu(e, conv.id)}
                  >
                    <MoreVertical size={16} />
                  </button>

                  {openMenuId === conv.id && (
                    <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-xl z-[100] min-w-[180px] py-1">
                      <button
                        className="w-full px-4 py-2.5 bg-transparent border-none text-gray-700 cursor-pointer transition-all duration-200 flex items-center gap-3 text-sm text-left hover:bg-gray-100"
                        onClick={(e) => handleRename(e, conv.id, conv.title)}
                      >
                        <Edit2 size={16} />
                        <span>Chỉnh sửa tiêu đề</span>
                      </button>
                      <button
                        className="w-full px-4 py-2.5 bg-transparent border-none text-red-500 cursor-pointer transition-all duration-200 flex items-center gap-3 text-sm text-left hover:bg-red-50"
                        onClick={(e) => handleDelete(e, conv.id, conv.title)}
                      >
                        <Trash2 size={16} />
                        <span>Xóa trò chuyện</span>
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Toggle Sidebar Button */}
      <button
        className="mx-4 mb-4 mt-auto px-4 py-3 bg-gray-200 hover:bg-gray-300 border-none rounded-xl text-gray-700 font-semibold flex items-center justify-center gap-2 cursor-pointer transition-all duration-300 flex-shrink-0 shadow-md hover:shadow-lg"
        onClick={() => setIsCollapsed(!isCollapsed)}
        title={isCollapsed ? "Mở sidebar" : "Đóng sidebar"}
      >
        {isCollapsed ? (
          <ChevronRight size={20} />
        ) : (
          <>
            <ChevronLeft size={20} />
            <span className="text-sm">Thu gọn</span>
          </>
        )}
      </button>

      <ConfirmDialog
        isOpen={deleteDialog.isOpen}
        title="Xóa cuộc trò chuyện"
        message={`Bạn có chắc chắn muốn xóa cuộc trò chuyện "${deleteDialog.title}"?`}
        confirmText="Xóa"
        cancelText="Hủy"
        variant="danger"
        onConfirm={confirmDelete}
        onCancel={cancelDelete}
      />

      <PromptDialog
        isOpen={renameDialog.isOpen}
        title="Chỉnh sửa tiêu đề"
        message="Nhập tiêu đề mới cho cuộc trò chuyện:"
        defaultValue={renameDialog.currentTitle}
        placeholder="Tiêu đề cuộc trò chuyện"
        confirmText="Lưu"
        cancelText="Hủy"
        onConfirm={confirmRename}
        onCancel={cancelRename}
      />
    </div>
  );
};

export default Sidebar;
