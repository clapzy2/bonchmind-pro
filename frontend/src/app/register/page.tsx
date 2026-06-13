"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AuthForm } from "@/components/auth-form";
import { useAuth } from "@/lib/auth-context";
import { EmailConflictError, RateLimitError, ValidationError } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const { user, loading, register } = useAuth();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && user !== null) {
      router.replace("/");
    }
  }, [loading, user, router]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError("Пароль должен быть не короче 8 символов.");
      return;
    }

    setBusy(true);
    try {
      await register({
        email: email.trim(),
        password,
        display_name: displayName.trim() || undefined,
      });
      // Backend sets the auth cookie on /api/auth/register, so we're already
      // signed in — go straight to the workspace.
      router.replace("/");
    } catch (err) {
      if (
        err instanceof EmailConflictError ||
        err instanceof ValidationError ||
        err instanceof RateLimitError
      ) {
        setError(err.message);
      } else {
        setError("Не удалось зарегистрироваться. Попробуйте ещё раз.");
      }
      setBusy(false);
    }
  }

  return (
    <AuthForm
      title="Регистрация"
      subtitle="Создайте аккаунт — у вас будет личное рабочее пространство для материалов."
      submitLabel="Зарегистрироваться"
      busy={busy}
      error={error}
      onSubmit={onSubmit}
      footer={
        <>
          Уже есть аккаунт?{" "}
          <Link href="/login" className="accent">
            Войти
          </Link>
        </>
      }
    >
      <label className="auth-field">
        <span className="auth-field-label">Email</span>
        <input
          type="email"
          autoComplete="email"
          required
          className="bm-control"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
        />
      </label>

      <label className="auth-field">
        <span className="auth-field-label">Имя (необязательно)</span>
        <input
          type="text"
          autoComplete="nickname"
          maxLength={120}
          className="bm-control"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          placeholder="Как к вам обращаться"
        />
      </label>

      <label className="auth-field">
        <span className="auth-field-label">Пароль</span>
        <input
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          maxLength={128}
          className="bm-control"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Минимум 8 символов"
        />
      </label>
    </AuthForm>
  );
}
