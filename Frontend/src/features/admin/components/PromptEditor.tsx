import { useState, useEffect } from "react";
import {
  FileText,
  Save,
  RefreshCw,
  ChevronDown,
  Check,
  AlertCircle,
} from "lucide-react";
import type { PromptItem, PromptUpdatePayload } from "../api/adminAPI";

interface PromptEditorProps {
  prompts: PromptItem[];
  isLoading: boolean;
  error: string | null;
  success: string | null;
  onUpdate: (
    intentName: string,
    payload: PromptUpdatePayload,
  ) => Promise<boolean>;
  onRefresh: () => Promise<void>;
}

// Human-friendly labels for intent names
const INTENT_LABELS: Record<string, string> = {
  general: "🔹 Tổng quát (General)",
  diem_chuan: "📊 Điểm chuẩn",
  hoc_phi: "💰 Học phí",
  career_advice: "💼 Tư vấn nghề nghiệp",
};

export const PromptEditor = ({
  prompts,
  isLoading,
  error,
  success,
  onUpdate,
  onRefresh,
}: PromptEditorProps) => {
  const [selectedIntent, setSelectedIntent] = useState<string>("");
  const [editedTemplate, setEditedTemplate] = useState<string>("");
  const [editedDescription, setEditedDescription] = useState<string>("");
  const [isSaving, setIsSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // Select first prompt on load
  useEffect(() => {
    if (prompts.length > 0 && !selectedIntent) {
      setSelectedIntent(prompts[0].intent_name);
    }
  }, [prompts, selectedIntent]);

  // Load selected prompt content into editor
  useEffect(() => {
    const prompt = prompts.find((p) => p.intent_name === selectedIntent);
    if (prompt) {
      setEditedTemplate(prompt.user_template);
      setEditedDescription(prompt.description);
      setHasChanges(false);
    }
  }, [selectedIntent, prompts]);

  const handleTemplateChange = (value: string) => {
    setEditedTemplate(value);
    const original = prompts.find((p) => p.intent_name === selectedIntent);
    setHasChanges(
      value !== original?.user_template ||
        editedDescription !== original?.description,
    );
  };

  const handleDescriptionChange = (value: string) => {
    setEditedDescription(value);
    const original = prompts.find((p) => p.intent_name === selectedIntent);
    setHasChanges(
      editedTemplate !== original?.user_template ||
        value !== original?.description,
    );
  };

  const handleSave = async () => {
    if (!selectedIntent || !hasChanges) return;

    setIsSaving(true);
    const payload: PromptUpdatePayload = {
      user_template: editedTemplate,
      description: editedDescription,
    };

    await onUpdate(selectedIntent, payload);
    setIsSaving(false);
    setHasChanges(false);
  };

  const selectedPrompt = prompts.find((p) => p.intent_name === selectedIntent);

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-gray-800 flex items-center gap-2">
          <FileText className="w-[18px] h-[18px] text-purple-600" />
          Nội dung Prompt Template
        </h2>
        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 hover:bg-gray-50 rounded-lg transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
          Làm mới
        </button>
      </div>

      {/* Status messages */}
      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-50 text-red-700 rounded-lg text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 p-3 bg-green-50 text-green-700 rounded-lg text-sm">
          <Check className="w-4 h-4 flex-shrink-0" />
          {success}
        </div>
      )}

      {/* Intent selector */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Chọn Intent
        </label>
        <div className="relative">
          <select
            value={selectedIntent}
            onChange={(e) => setSelectedIntent(e.target.value)}
            className="w-full appearance-none bg-white border border-gray-200 rounded-lg px-4 py-2.5 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500"
          >
            {prompts.map((p) => (
              <option key={p.intent_name} value={p.intent_name}>
                {INTENT_LABELS[p.intent_name] || p.intent_name}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
        </div>
      </div>

      {/* Description */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Mô tả
        </label>
        <input
          type="text"
          value={editedDescription}
          onChange={(e) => handleDescriptionChange(e.target.value)}
          className="w-full border border-gray-200 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500"
          placeholder="Mô tả ngắn cho prompt này..."
        />
      </div>

      {/* Prompt template editor */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-medium text-gray-700">
            Nội dung Prompt (User Template)
          </label>
          {selectedPrompt && (
            <span className="text-xs text-gray-500 bg-gray-50 px-2 py-1 rounded">
              Cập nhật:{" "}
              {new Date(selectedPrompt.updated_at).toLocaleDateString("vi-VN", {
                day: "2-digit",
                month: "2-digit",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          )}
        </div>
        <textarea
          value={editedTemplate}
          onChange={(e) => handleTemplateChange(e.target.value)}
          rows={14}
          className="w-full bg-gray-50 border border-gray-200 rounded-lg px-4 py-3 text-sm font-mono text-gray-800 leading-relaxed focus:bg-white focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500 resize-y"
          placeholder="Nhập nội dung prompt template..."
        />
      </div>

      {/* Save button */}
      <div className="flex justify-end pt-2 border-t border-gray-100">
        <button
          onClick={handleSave}
          disabled={!hasChanges || isSaving}
          className={`flex items-center gap-2 px-5 py-2.5 mt-4 rounded-lg text-sm font-medium transition-colors ${
            hasChanges
              ? "bg-purple-600 text-white hover:bg-purple-700 shadow-sm"
              : "bg-gray-100 text-gray-400 cursor-not-allowed"
          }`}
        >
          {isSaving ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          {isSaving ? "Đang lưu..." : "Lưu thay đổi"}
        </button>
      </div>
    </div>
  );
};
