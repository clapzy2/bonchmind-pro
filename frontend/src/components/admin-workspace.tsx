"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { DatabaseZap, RefreshCw, ShieldCheck } from "lucide-react";

import {
  getAdminStats,
  getAdminUsers,
  getAuditEvents,
  getLatestDiagnostics,
  reconcileDatabase,
  setUserActive,
  setUserRole,
  UnauthorizedError,
  type AdminStats,
  type AdminUser,
  type AuditEvent,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { handleAuthError } from "@/lib/handle-auth-error";
import { RunDiagnostics } from "@/components/run-diagnostics";

/**
 * Superuser-only admin screen (Stage 9b; user-management added in Stage 13).
 * Instance-wide counts, the recent audit log, the latest run diagnostics
 * (reusing ``RunDiagnostics``), the "Сверить базу" reconcile, and the
 * **Пользователи** table (promote/demote + ban/unban, with the self-row
 * disabled). The first superuser is still bootstrapped via the DB (see README).
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

type AdminWorkspaceProps = {
  /**
   * Refresh the shared shell state (materials + system status) after a
   * reconcile. Without this the SourcePanel's "Материалов в базе" on other
   * tabs keeps the pre-reconcile count until an F5, even though the scrub
   * already dropped the orphan chunks.
   */
  onReconciled?: () => Promise<void> | void;
};

export function AdminWorkspace({ onReconciled }: AdminWorkspaceProps) {
  const router = useRouter();
  const { user: me } = useAuth();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [diagnostics, setDiagnostics] = useState("");
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [userBusy, setUserBusy] = useState<string | null>(null);
  const [userNotice, setUserNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reconciling, setReconciling] = useState(false);
  const [reconcileNotice, setReconcileNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextStats, nextEvents, nextDiag, nextUsers] = await Promise.all([
        getAdminStats(),
        getAuditEvents(100),
        // Diagnostics are nice-to-have — never fail the whole screen over them.
        getLatestDiagnostics().catch(() => ""),
        getAdminUsers(),
      ]);
      setStats(nextStats);
      setEvents(nextEvents);
      setDiagnostics(nextDiag);
      setUsers(nextUsers);
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

  const reconcile = useCallback(async () => {
    setReconciling(true);
    setReconcileNotice(null);
    try {
      const { total_removed_chunks: chunks, total_removed_documents: docs } =
        await reconcileDatabase();
      setReconcileNotice(
        chunks > 0
          ? `Удалено осиротевших фрагментов: ${chunks} (документов: ${docs}). База синхронизирована.`
          : "Орфанов не найдено — база уже синхронизирована.",
      );
      // Refresh the admin stats and the shared shell state (the latter so the
      // SourcePanel's "Материалов в базе" on other tabs drops to match,
      // instead of showing the stale pre-reconcile count until an F5).
      await Promise.all([load(), Promise.resolve(onReconciled?.())]);
    } catch (err) {
      if (handleAuthError(err, router)) {
        return;
      }
      setReconcileNotice(
        "Не удалось выполнить сверку базы. Проверьте backend и права доступа.",
      );
    } finally {
      setReconciling(false);
    }
  }, [load, onReconciled, router]);

  const refreshUsers = useCallback(async () => {
    try {
      setUsers(await getAdminUsers());
    } catch {
      // non-fatal; the table just keeps its previous state
    }
  }, []);

  const toggleRole = useCallback(
    async (target: AdminUser) => {
      const makeAdmin = !target.is_superuser;
      if (!makeAdmin && !window.confirm(`Снять права администратора у ${target.email}?`)) {
        return;
      }
      setUserNotice(null);
      setUserBusy(target.id);
      try {
        await setUserRole(target.id, makeAdmin);
        await refreshUsers();
      } catch (err) {
        if (handleAuthError(err, router)) {
          return;
        }
        setUserNotice(`Не удалось изменить роль пользователя ${target.email}.`);
      } finally {
        setUserBusy(null);
      }
    },
    [refreshUsers, router],
  );

  const toggleActive = useCallback(
    async (target: AdminUser) => {
      const activate = !target.is_active;
      if (!activate && !window.confirm(`Заблокировать ${target.email}? Он будет немедленно отключён.`)) {
        return;
      }
      setUserNotice(null);
      setUserBusy(target.id);
      try {
        await setUserActive(target.id, activate);
        await refreshUsers();
      } catch (err) {
        if (handleAuthError(err, router)) {
          return;
        }
        setUserNotice(`Не удалось изменить статус пользователя ${target.email}.`);
      } finally {
        setUserBusy(null);
      }
    },
    [refreshUsers, router],
  );

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
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="bm-button-secondary inline-flex items-center gap-2"
            onClick={reconcile}
            disabled={reconciling || loading}
            title="Удалить из векторной базы фрагменты, у которых больше нет материала в библиотеке"
          >
            <DatabaseZap size={15} className={reconciling ? "animate-pulse" : ""} />
            {reconciling ? "Сверяю…" : "Сверить базу"}
          </button>
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
      </div>

      {error ? (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          {error}
        </div>
      ) : null}

      {reconcileNotice ? (
        <div className="rounded-md border border-cyan-500/30 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-100">
          {reconcileNotice}
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

      <div className="bm-surface rounded-xl p-4 shadow-soft">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Пользователи</h2>
          <span className="text-xs muted">{users.length}</span>
        </div>

        {userNotice ? (
          <div className="mb-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
            {userNotice}
          </div>
        ) : null}

        {users.length === 0 ? (
          <div className="rounded-md border border-dashed border-[var(--line)] p-4 text-sm muted">
            {loading ? "Загружаю пользователей…" : "Пользователей нет."}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide muted">
                  <th className="px-2 py-2 font-semibold">Email</th>
                  <th className="px-2 py-2 font-semibold">Тариф</th>
                  <th className="px-2 py-2 font-semibold">Статус</th>
                  <th className="px-2 py-2 font-semibold">Роль</th>
                  <th className="px-2 py-2 text-right font-semibold">Действия</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const isSelf = u.id === me?.id;
                  const busy = userBusy === u.id;
                  // Self and the configured root admin can't be modified here.
                  const locked = isSelf || u.is_protected;
                  return (
                    <tr key={u.id} className="border-t border-[var(--line)]">
                      <td className="px-2 py-2 text-slate-200">
                        {u.email}
                        {isSelf ? (
                          <span className="ml-2 text-xs muted">(это вы)</span>
                        ) : u.is_protected ? (
                          <span className="ml-2 text-xs text-emerald-300">(защищён)</span>
                        ) : null}
                      </td>
                      <td className="px-2 py-2 text-slate-300">{u.plan}</td>
                      <td className="px-2 py-2">
                        <span className={`bm-chip ${u.is_active ? "bm-chip-ready" : "bm-chip-limited"}`}>
                          {u.is_active ? "Активен" : "Заблокирован"}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-slate-300">{u.is_superuser ? "Админ" : "Пользователь"}</td>
                      <td className="px-2 py-2">
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => toggleRole(u)}
                            disabled={locked || busy}
                            className="bm-button-secondary h-8 px-2.5 text-xs disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {u.is_superuser ? "Снять админа" : "Сделать админом"}
                          </button>
                          <button
                            type="button"
                            onClick={() => toggleActive(u)}
                            disabled={locked || busy}
                            className={`h-8 rounded-md px-2.5 text-xs disabled:cursor-not-allowed disabled:opacity-50 ${
                              u.is_active ? "bm-button-danger text-red-100" : "bm-button-secondary"
                            }`}
                          >
                            {u.is_active ? "Заблокировать" : "Разблокировать"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
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
