import { UnauthorizedError } from "@/lib/api";

/**
 * Minimal "redirect on 401" helper for catch blocks.
 *
 * The whole UI shares the same recovery: if we see an UnauthorizedError —
 * meaning the session cookie is missing/expired — bounce the user to /login.
 * Returns ``true`` if it handled the error so the caller can early-return
 * without running its normal warning/state-update path.
 *
 * Typed loosely on the router param so any object with ``replace`` (the
 * ``next/navigation`` ``useRouter`` return value, our auth-context router,
 * a test stub, …) works without dragging Next types into the lib layer.
 */
export type AuthErrorRouter = {
  replace: (url: string) => void;
};

export function handleAuthError(error: unknown, router: AuthErrorRouter): boolean {
  if (error instanceof UnauthorizedError) {
    router.replace("/login");
    return true;
  }
  return false;
}
