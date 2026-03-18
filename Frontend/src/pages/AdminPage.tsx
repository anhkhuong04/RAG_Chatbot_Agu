import { useState } from "react";
import { CheckCircle, AlertCircle, LogOut } from "lucide-react";
import {
  UploadForm,
  DocumentList,
  PromptManager,
  Sidebar,
} from "../features/admin/components";
import type { AdminTab } from "../features/admin/components/Sidebar";
import { getDefaultFormData } from "../features/admin/components/UploadForm";
import { useDocuments } from "../features/admin/hooks/useDocuments";
import { usePrompts } from "../features/admin/hooks/usePrompts";
import { useAuthStore } from "../features/auth/store/useAuthStore";
import type { UploadFormData } from "../types/admin";
import type { PromptUpdatePayload } from "../features/admin/api/adminAPI";
import LoginForm from "../features/auth/components/LoginForm";

/**
 * Admin Page - Knowledge Base Management Dashboard
 * Sidebar layout with tab-based content routing.
 */
const AdminPage = () => {
  const { isAuthenticated, isLoggingIn, loginError, login, logout } =
    useAuthStore();

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
    uploadError,
    uploadSuccess,
    deleteDocument,
    refetchDocuments,
    uploadDocument,
    resetUploadState,
  } = useDocuments();

  const {
    prompts,
    isLoadingPrompts,
    promptError,
    updateSuccess,
    updatePrompt,
    refetchPrompts,
    resetUpdateState,
  } = usePrompts();

  // Compat assignments
  const error = uploadError;
  const promptSuccess = updateSuccess;
  const fetchDocuments = async () => {
    await refetchDocuments();
  };
  const fetchPrompts = async () => {
    await refetchPrompts();
  };

  const handleUpload = async (formData: UploadFormData) => {
    try {
      await uploadDocument(formData);
      return true;
    } catch {
      return false;
    }
  };

  const handleDelete = async (docUuid: string) => {
    try {
      await deleteDocument(docUuid);
      return true;
    } catch {
      return false;
    }
  };

  const handleUpdatePrompt = async (
    intentName: string,
    payload: PromptUpdatePayload,
  ) => {
    try {
      await updatePrompt({ intentName, payload });
      return true;
    } catch {
      return false;
    }
  };

  const clearMessages = () => {
    resetUploadState();
    resetUpdateState();
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Sidebar */}
      <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Main Content */}
      <main className="ml-64 min-h-screen flex flex-col">
        {/* Global Page Header */}
        <header className="sticky top-0 z-20 bg-white border-b border-gray-100 px-8 py-4 flex items-center justify-between shadow-sm">
          <div>
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
              <span>Admin Dashboard</span>
              <span>/</span>
              <span className="text-purple-600 font-medium">
                {activeTab === "overview" && "Tổng quan"}
                {activeTab === "knowledge" && "Quản lý Tri thức"}
                {activeTab === "prompts" && "Cấu hình Prompt"}
              </span>
            </div>
            <h1 className="text-2xl font-bold text-gray-900">
              {activeTab === "overview" && "Tổng quan hệ thống"}
              {activeTab === "knowledge" && "Quản lý Cơ sở Tri thức"}
              {activeTab === "prompts" && "Cấu hình & Quản lý Prompt"}
            </h1>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={logout}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-600 bg-red-50 hover:bg-red-100 rounded-lg transition-colors"
            >
              <LogOut className="w-4 h-4" />
              Đăng xuất
            </button>
          </div>
        </header>

        <div className="p-8 flex-1">
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
