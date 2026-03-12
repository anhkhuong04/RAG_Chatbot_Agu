import { useState } from "react";
import { CheckCircle, AlertCircle, LogOut } from "lucide-react";
import {
  UploadForm,
  DocumentList,
  PromptManager,
  Sidebar,
  LoginForm,
} from "../components/admin";
import type { AdminTab } from "../components/admin";
import { useAdmin, getDefaultFormData } from "../hooks/useAdmin";
import { useAuth } from "../hooks/useAuth";

/**
 * Admin Page - Knowledge Base Management Dashboard
 * Sidebar layout with tab-based content routing.
 */
const AdminPage = () => {
  const { isAuthenticated, isLoggingIn, loginError, login, logout } = useAuth();

  if (!isAuthenticated) {
    return (
      <LoginForm onLogin={login} isLoggingIn={isLoggingIn} error={loginError} />
    );
  }

  return <AdminDashboard logout={logout} />;
};

const AdminDashboard = ({ logout }: { logout: () => void }) => {
  const [activeTab, setActiveTab] = useState<AdminTab>("knowledge");

  const {
    documents,
    isLoading,
    isUploading,
    error,
    uploadSuccess,
    prompts,
    isLoadingPrompts,
    promptError,
    promptSuccess,
    fetchDocuments,
    handleUpload,
    handleDelete,
    clearMessages,
    fetchPrompts,
    handleUpdatePrompt,
  } = useAdmin();

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Sidebar */}
      <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Main Content */}
      <main className="ml-64 min-h-screen">
        {/* Top Bar */}
        <header className="sticky top-0 z-10 bg-white/80 backdrop-blur border-b border-gray-100 px-8 h-14 flex items-center">
          <h1 className="text-sm font-semibold text-gray-700 flex-1">
            {activeTab === "overview" && "Tổng quan"}
            {activeTab === "knowledge" && "Quản lý Tri thức"}
            {activeTab === "prompts" && "Cấu hình Prompt"}
          </h1>
          <button
            onClick={logout}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-red-600 transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Đăng xuất
          </button>
        </header>

        <div className="p-8">
          {/* Alert Messages */}
          {(error || uploadSuccess) && (
            <div className="mb-6 space-y-3">
              {error && (
                <div className="flex items-center gap-3 p-3.5 bg-red-50 border border-red-100 rounded-xl">
                  <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                  <p className="text-sm text-red-700 flex-1">{error}</p>
                  <button
                    onClick={clearMessages}
                    className="text-red-400 hover:text-red-600 text-xs font-medium"
                  >
                    Đóng
                  </button>
                </div>
              )}

              {uploadSuccess && (
                <div className="flex items-center gap-3 p-3.5 bg-emerald-50 border border-emerald-100 rounded-xl">
                  <CheckCircle className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                  <p className="text-sm text-emerald-700 flex-1">
                    {uploadSuccess}
                  </p>
                  <button
                    onClick={clearMessages}
                    className="text-emerald-400 hover:text-emerald-600 text-xs font-medium"
                  >
                    Đóng
                  </button>
                </div>
              )}
            </div>
          )}

          {/* ===== Tab: Tổng quan ===== */}
          {activeTab === "overview" && (
            <div className="space-y-6">
              <DocumentList
                documents={documents}
                isLoading={isLoading}
                onDelete={handleDelete}
                onRefresh={fetchDocuments}
              />
            </div>
          )}

          {/* ===== Tab: Quản lý Tri thức ===== */}
          {activeTab === "knowledge" && (
            <div className="space-y-6">
              {/* Upload + Document List grid */}
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                {/* Upload Form - 1/3 */}
                <div className="xl:col-span-1">
                  <UploadForm
                    onSubmit={handleUpload}
                    isUploading={isUploading}
                    defaultValues={getDefaultFormData()}
                  />
                </div>

                {/* Document List - 2/3 */}
                <div className="xl:col-span-2">
                  <DocumentList
                    documents={documents}
                    isLoading={isLoading}
                    onDelete={handleDelete}
                    onRefresh={fetchDocuments}
                  />
                </div>
              </div>
            </div>
          )}

          {/* ===== Tab: Cấu hình Prompt ===== */}
          {activeTab === "prompts" && (
            <PromptManager
              prompts={prompts}
              isLoading={isLoadingPrompts}
              error={promptError}
              success={promptSuccess}
              onUpdate={handleUpdatePrompt}
              onRefresh={fetchPrompts}
            />
          )}
        </div>
      </main>
    </div>
  );
};

export default AdminPage;
