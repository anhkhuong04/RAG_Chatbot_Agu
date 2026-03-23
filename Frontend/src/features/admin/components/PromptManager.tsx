import { PromptEditor } from "./PromptEditor";
import type { PromptItem, PromptUpdatePayload } from "../api/adminAPI";

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
  return <PromptEditor {...props} />;
};
