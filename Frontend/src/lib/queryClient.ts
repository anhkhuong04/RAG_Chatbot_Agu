import { QueryClient } from "@tanstack/react-query";

/**
 * Global QueryClient instance for React Query
 * Configured with sensible defaults for data fetching and caching
 */
export const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            refetchOnWindowFocus: false, // Don't refetch when switching tabs
            retry: 1, // Optional: Retry failed queries once
            staleTime: 5 * 60 * 1000, // Data is fresh for 5 minutes
        },
        mutations: {
            retry: 0, // Never retry mutations automatically
        },
    },
});
