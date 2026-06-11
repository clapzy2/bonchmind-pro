"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  getMe,
  loginUser,
  logoutUser,
  registerUser,
  type LoginPayload,
  type RegisterPayload,
  type UserOut,
} from "@/lib/api";

/**
 * AuthContext is the single source of truth for "who is the current user".
 *
 * Bootstrap flow:
 *   1. Provider mounts -> ``getMe()`` is called once. Backend returns the
 *      user if the cookie is valid, or ``null`` (we treat as anonymous).
 *   2. ``loading`` stays ``true`` until that first probe resolves so the
 *      rest of the UI can render a splash instead of flashing /login.
 *
 * The provider exposes the same login / register / logout primitives used
 * by the auth forms; on success they update internal state so the rest of
 * the tree (Topbar, protected pages) re-renders without an extra round
 * trip. Errors propagate to the caller — the forms render targeted copy
 * for ``InvalidCredentialsError`` / ``EmailConflictError`` while the
 * provider stays UI-agnostic.
 */

type AuthContextValue = {
  user: UserOut | null;
  loading: boolean;
  refresh: () => Promise<void>;
  login: (payload: LoginPayload) => Promise<UserOut>;
  register: (payload: RegisterPayload) => Promise<UserOut>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const me = await getMe();
    setUser(me);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const me = await getMe();
      if (!cancelled) {
        setUser(me);
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (payload: LoginPayload) => {
    const next = await loginUser(payload);
    setUser(next);
    return next;
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    const next = await registerUser(payload);
    setUser(next);
    return next;
  }, []);

  const logout = useCallback(async () => {
    await logoutUser();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, refresh, login, register, logout }),
    [user, loading, refresh, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return ctx;
}
