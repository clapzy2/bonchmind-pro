"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, LogOut } from "lucide-react";

import type { ApiHealth } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { WorkspaceSection } from "@/lib/workspace-section";

type TopbarProps = {
  activeSection: WorkspaceSection;
  health: ApiHealth;
};

const sectionTitles: Record<WorkspaceSection, { label: string; subtitle: string }> = {
  summary: {
    label: "Конспект по учебным материалам",
    subtitle: "Рабочая область",
  },
  assistant: {
    label: "Ассистент по материалам",
    subtitle: "Диалоговая рабочая зона",
  },
  materials: {
    label: "Библиотека материалов",
    subtitle: "Живая структура базы знаний",
  },
  admin: {
    label: "Администрирование",
    subtitle: "Только для администратора",
  },
};

export function Topbar({ activeSection, health }: TopbarProps) {
  const router = useRouter();
  const { user, logout } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);

  const online = health.status === "ok";
  const copy = sectionTitles[activeSection];
  const stationLabel = online ? "Станция готова к работе" : "Backend недоступен";

  async function onLogout() {
    setLoggingOut(true);
    try {
      await logout();
    } catch {
      // Even if the backend call fails (e.g. already expired), clear local
      // state by going to /login — the AuthProvider will re-probe and find
      // null.
    }
    router.replace("/login");
  }

  const displayName = user?.display_name?.trim() || user?.email || "";
  const workspaceName = user?.personal_workspace?.name || "";

  return (
    <header className="topbar">
      <div className="min-w-0">
        <div className="text-xs font-semibold uppercase tracking-[0.16em] muted">{copy.subtitle}</div>
        <div className="truncate pt-1 text-lg font-semibold text-white">{copy.label}</div>
        <div className="pt-1 text-sm muted">
          {online ? stationLabel : "Запусти API, чтобы снова генерировать конспекты и ответы."}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className={`pill ${online ? "pill-good" : "pill-warn"}`}>
          <Activity size={15} />
          {online ? "Готово" : "Offline"}
        </span>

        {user ? (
          <div className="topbar-user" title={user.email}>
            <div className="topbar-user-name">{displayName}</div>
            {workspaceName ? <div className="topbar-user-workspace muted">{workspaceName}</div> : null}
          </div>
        ) : null}

        {user ? (
          <button
            type="button"
            className="bm-button-secondary topbar-logout"
            onClick={onLogout}
            disabled={loggingOut}
            aria-label="Выйти"
          >
            <LogOut size={15} />
            {loggingOut ? "..." : "Выйти"}
          </button>
        ) : null}
      </div>
    </header>
  );
}
