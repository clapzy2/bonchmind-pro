"use client";

import type { ReactNode } from "react";

import { AuthProvider } from "@/lib/auth-context";

/**
 * Client-only provider chain.
 *
 * Lives in its own ``"use client"`` file so ``layout.tsx`` can stay a
 * server component (keeps page metadata + static rendering for the shell)
 * and only the auth context bootstraps on the client.
 *
 * Future client-side providers (theme, toast, etc.) get added here.
 */
export function Providers({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
