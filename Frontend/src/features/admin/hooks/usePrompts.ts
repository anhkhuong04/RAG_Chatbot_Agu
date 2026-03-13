import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getPrompts, updatePrompt, type PromptUpdatePayload } from "../api/adminAPI";

export const usePrompts = () => {
    const queryClient = useQueryClient();

    const promptsQuery = useQuery({
        queryKey: ["prompts"],
        queryFn: getPrompts,
    });

    const updateMutation = useMutation({
        mutationFn: ({ intentName, payload }: { intentName: string; payload: PromptUpdatePayload }) =>
            updatePrompt(intentName, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["prompts"] });
        },
    });

    return {
        prompts: promptsQuery.data || [],
        isLoadingPrompts: promptsQuery.isPending || promptsQuery.isFetching,
        promptError: promptsQuery.error ? "Không thể tải danh sách prompts." : null,

        isUpdating: updateMutation.isPending,
        updateError: updateMutation.error ? "Lỗi khi cập nhật prompt." : null,
        updateSuccess: updateMutation.isSuccess ? "Đã cập nhật prompt thành công!" : null,

        updatePrompt: updateMutation.mutateAsync,
        refetchPrompts: promptsQuery.refetch,
        resetUpdateState: updateMutation.reset,
    };
};
