import { Activity } from "lucide-react";
import type { ApiHealth } from "@/lib/api";
import type { WorkspaceSection } from "@/components/workspace-sections";

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
  quality: {
    label: "Проверка качества",
    subtitle: "Надежность и покрытие",
  },
  settings: {
    label: "Настройки станции",
    subtitle: "Системный слой",
  },
};

export function Topbar({ activeSection, health }: TopbarProps) {
  const online = health.status === "ok";
  const copy = sectionTitles[activeSection];
  const stationLabel = online ? "Станция готова к работе" : "Backend недоступен";

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
      </div>
    </header>
  );
}
