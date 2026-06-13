"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw, ShieldCheck } from "lucide-react";

import {
  getAdminStats,
  getAuditEvents,
  getLatestDiagnostics,
  UnauthorizedError,
  type AdminStats,
  type AuditEvent,
} from "@/lib/api";
import { handleAuthError } from "@/lib/handle-auth-error";
import { RunDiagnostics } from "@/components/run-diagnostics";

/**
 * Superuser-only admin screen (Stage 9b). Read-only overview of the instance:
 * system-wide counts, the recent audit log, and the latest run diagnostics
 * (reusing the collapsible ``RunDiagnostics`` panel). No mutations here — role
 * management, bans and rate-limit tuning are deliberately out of scope; the
 * first superuser is promoted via the DB directly (see README).
 *
 * The backend gates every ``/api/admin/*`` call with ``require_superuser``, so
 * this component is the convenience layer, not the security boundary: a 403
 * surfaces as a generic error, a 401 bounces to /login.
 */

const ACTION_LABELS: Record<string, string> = {
  login: "Вход",
  upload: "Загрузка",
  delete: "Удаление",
  reindex: "Переиндексация",
};

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function shortId(value: string | null): string {
  if (!value) {
    return "—";
  }
  return value.length > 8 ? `${value.slice(0, 8)}…` : value;
}

export function AdminWorkspace() {
  const router = useRouter();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [diagnostics, setDiagnostics] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextStats, nextEvents, nextDiag] = await Promise.all([
        getAdminStats(),
        getAuditEvents(100),
        // Diagnostics are nice-to-have — never fail the whole screen over them.
        getLatestDiagnostics().catch(() => ""),
      ]);
      setStats(nextStats);
      setEvents(nextEvents);
      setDiagnostics(nextDiag);
    } catch (err) {
      if (handleAuthError(err, router)) {
        return;
      }
      if (err instanceof UnauthorizedError) {
        return;
      }
      setError(
        "Не удалось загрузить данные администрирования. Проверьте backend и права доступа.",
      );
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    // Wrapped in an inline async IIFE so the synchronous setState at the top
    // of ``load`` isn't flagged as a cascading-render risk — same pattern as
    // the initial fetch in app/page.tsx. ``load`` has its own try/catch, so
    // the floating promise can't reject.
    (async () => {
      await load();
    })();
  }, [load]);

  const statCards = stats
    ? [
        { label: "Пользователи", value: stats.users },
        { label: "Рабочие пространства", value: stats.workspaces },
        { label: "Документы", value: stats.documents },
        { label: "Событий аудита", value: stats.audit_events },
      ]
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="accent" size={20} />
          <h1 className="text-xl font-bold text-white">Администрирование</h1>
        </div>
        <button
          type="button"
          className="bm-button-secondary inline-flex items-center gap-2"
          onClick={load}
          disabled={loading}
        >
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          Обновить
        </button>
      </div>

      {error ? (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          {error}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.length > 0 ? (
          statCards.map((card) => (
            <div key={card.label} className="bm-surface rounded-xl p-4 shadow-soft">
              <div className="text-sm muted">{card.label}</div>
              <div className="mt-2 text-3xl font-bold text-white">{card.value}</div>
            </div>
          ))
        ) : (
          <div className="bm-surface rounded-xl p-4 text-sm muted sm:col-span-2 lg:col-span-4">
            {loading ? "Загружаю статистику…" : "Статистика недоступна."}
          </div>
        )}
      </div>

      <div className="bm-surface rounded-xl p-4 shadow-soft">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Журнал аудита</h2>
          <span className="text-xs muted">последние {events.length}</span>
        </div>

        {events.length === 0 ? (
          <div className="rounded-md border border-dashed border-[var(--line)] p-4 text-sm muted">
            {loading ? "Загружаю события…" : "Событий пока нет."}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide muted">
                  <th className="px-2 py-2 font-semibold">Время</th>
                  <th className="px-2 py-2 font-semibold">Действие</th>
                  <th className="px-2 py-2 font-semibold">Пользователь</th>
                  <th className="px-2 py-2 font-semibold">Объект</th>
                  <th className="px-2 py-2 font-semibold">IP</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.id} className="border-t border-[var(--line)]">
                    <td className="whitespace-nowrap px-2 py-2 text-slate-300">
                      {formatTime(event.created_at)}
                    </td>
                    <td className="px-2 py-2">
                      <span className="rounded-lg border border-white/10 bg-[#0d1117] px-2 py-1 text-xs font-semibold text-slate-200">
                        {actionLabel(event.action)}
                      </span>
                    </td>
                    <td
                      className="whitespace-nowrap px-2 py-2 font-mono text-xs text-slate-300"
                      title={event.user_id ?? ""}
                    >
                      {shortId(event.user_id)}
                    </td>
                    <td
                      className="max-w-[220px] truncate px-2 py-2 text-slate-200"
                      title={event.target}
                    >
                      {event.target || "—"}
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 font-mono text-xs text-slate-400">
                      {event.ip || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <RunDiagnostics
        title="Последняя диагностика запуска"
        strengths={[]}
        warnings={[]}
        diagnostics={diagnostics}
      />
    </div>
  );
}
