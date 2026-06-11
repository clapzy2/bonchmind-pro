"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AuthForm } from "@/components/auth-form";
import { useAuth } from "@/lib/auth-context";
import { InvalidCredentialsError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { user, loading, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // If the bootstrap probe finds an existing session, skip the form entirely.
  useEffect(() => {
    if (!loading && user !== null) {
      router.replace("/");
    }
  }, [loading, user, router]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login({ email: email.trim(), password });
      router.replace("/");
    } catch (err) {
      if (err instanceof InvalidCredentialsError) {
        setError(err.message);
      } else {
        setError("Не удалось войти. Попробуйте ещё раз.");
      }
      setBusy(false);
    }
  }

  return (
    <AuthForm
      title="Вход"
      subtitle="Войдите, чтобы продолжить работу с материалами."
      submitLabel="Войти"
      busy={busy}
      error={error}
      onSubmit={onSubmit}
      footer={
        <>
          Нет аккаунта?{" "}
          <Link href="/register" className="accent">
            Создать аккаунт
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
        <span className="auth-field-label">Пароль</span>
        <input
          type="password"
          autoComplete="current-password"
          required
          minLength={1}
          className="bm-control"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="••••••••"
        />
      </label>
    </AuthForm>
  );
}
