import { PromptEditor } from "./PromptEditor";
import type { PromptItem, PromptUpdatePayload } from "../../services/adminAPI";

interface PromptManagerProps {
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

export const PromptManager = (props: PromptManagerProps) => {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-gray-800">Cấu hình Prompt</h2>
        <p className="text-sm text-gray-500 mt-1">
          Quản lý và chỉnh sửa prompt template cho từng loại intent
        </p>
      </div>
      <PromptEditor {...props} />
    </div>
  );
};
