"use client";

import type { FormEvent, ReactNode } from "react";

type AuthFormProps = {
  title: string;
  subtitle?: string;
  submitLabel: string;
  busy: boolean;
  error?: string | null;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  /** The input rows — typically a stack of <label><input/></label>. */
  children: ReactNode;
  /** The "alternate action" row at the bottom (e.g. "уже есть аккаунт?"). */
  footer?: ReactNode;
};

/**
 * Shared visual scaffold for the login / register pages.
 *
 * Centred card on the page, reusing the project's ``panel`` and
 * ``bm-button-primary`` styles so the auth screens match the rest of the UI.
 * Error rendering is centralised here so the pages only need to map a typed
 * error (InvalidCredentialsError / EmailConflictError / generic Error) to a
 * Russian string and pass it in.
 */
export function AuthForm({
  title,
  subtitle,
  submitLabel,
  busy,
  error,
  onSubmit,
  children,
  footer,
}: AuthFormProps) {
  return (
    <main className="auth-page">
      <form className="auth-card panel" onSubmit={onSubmit} noValidate>
        <div className="auth-card-head">
          <h1 className="auth-title">{title}</h1>
          {subtitle ? <p className="auth-subtitle muted">{subtitle}</p> : null}
        </div>

        <div className="auth-card-body">{children}</div>

        {error ? (
          <div className="auth-error" role="alert">
            {error}
          </div>
        ) : null}

        <button type="submit" className="bm-button-primary auth-submit" disabled={busy}>
          {busy ? "..." : submitLabel}
        </button>

        {footer ? <div className="auth-card-foot muted">{footer}</div> : null}
      </form>
    </main>
  );
}
