import {
  LayoutDashboard,
  BookOpen,
  Settings,
  MessageSquare,
} from "lucide-react";
import { Link } from "react-router-dom";

export type AdminTab = "overview" | "knowledge" | "prompts";

interface SidebarProps {
  activeTab: AdminTab;
  onTabChange: (tab: AdminTab) => void;
}

const NAV_ITEMS: { id: AdminTab; label: string; icon: React.ElementType }[] = [
  { id: "overview", label: "Tổng quan", icon: LayoutDashboard },
  { id: "knowledge", label: "Quản lý Tri thức", icon: BookOpen },
  { id: "prompts", label: "Cấu hình Prompt", icon: Settings },
];

export const Sidebar = ({ activeTab, onTabChange }: SidebarProps) => {
  return (
    <aside className="fixed left-0 top-0 bottom-0 w-64 bg-white border-r border-gray-200 flex flex-col z-20">
      {/* Logo / Brand */}
      <div className="h-16 px-5 flex items-center gap-3 border-b border-gray-100">
        <div className="w-9 h-9 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl flex items-center justify-center">
          <BookOpen className="w-[18px] h-[18px] text-white" />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-bold text-gray-800">Knowledge Base</p>
          <p className="text-[11px] text-gray-400">Admin Dashboard</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
          const isActive = activeTab === id;
          return (
            <button
              key={id}
              onClick={() => onTabChange(id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-blue-50 text-blue-700"
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-800"
              }`}
            >
              <Icon
                className={`w-[18px] h-[18px] ${isActive ? "text-blue-600" : "text-gray-400"}`}
              />
              {label}
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-3 py-4 border-t border-gray-100">
        <Link
          to="/chat"
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-50 hover:text-gray-800 transition-colors"
        >
          <MessageSquare className="w-[18px] h-[18px] text-gray-400" />
          Mở Chatbot
        </Link>
      </div>
    </aside>
  );
};
