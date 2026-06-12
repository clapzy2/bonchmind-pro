"use client";

import { BookOpenText, FileSearch, MessageSquareQuote, Sparkles } from "lucide-react";

import type { SummaryResponse, SystemStatus, TraceChunk, TraceChunkGroup } from "@/lib/api";
import type { WorkspaceSection } from "@/lib/workspace-section";

type SourcePanelProps = {
  activeSection: WorkspaceSection;
  status: SystemStatus;
  lastRun: SummaryResponse | null;
};

type CoverageCard = {
  title: string;
  meta: string;
  detail: string;
};

function isChunkGroupArray(value: TraceChunk[] | TraceChunkGroup[] | undefined): value is TraceChunkGroup[] {
  return Array.isArray(value) && value.length > 0 && "chunks" in value[0];
}

function buildCoverageCards(lastRun: SummaryResponse | null): CoverageCard[] {
  const plannedGroups = lastRun?.trace?.chunks?.planned_chunk_groups;
  if (!isChunkGroupArray(plannedGroups)) {
    return [];
  }

  // Only surface plan items that are actually backed by chunks. The planner
  // emits items even when retrieval finds nothing (e.g. an off-topic request
  // against an unrelated material); presenting those empty groups as "опора
  // ответа" is misleading — Stage 7d smoke caught exactly this.
  return plannedGroups
    .filter((group) => group.chunks.length > 0)
    .slice(0, 4)
    .map((group) => {
      const sections = Array.from(new Set(group.chunks.map((chunk) => chunk.section).filter(Boolean)));

      return {
        title: group.item || "Пункт плана",
        meta: sections.slice(0, 2).join("; ") || "Без точных разделов",
        detail: `${group.chunks.length} фрагм. поддерживают этот блок ответа.`,
      };
    });
}

const panelCopy: Record<WorkspaceSection, { eyebrow: string; title: string; body: string; icon: typeof Sparkles }> = {
  summary: {
    eyebrow: "Источники",
    title: "Опора ответа",
    body: "Здесь видно, чем подтвержден последний конспект.",
    icon: FileSearch,
  },
  assistant: {
    eyebrow: "Ассистент",
    title: "Как лучше спрашивать",
    body: "Короткие follow-up вопросы почти всегда сильнее одного длинного запроса.",
    icon: MessageSquareQuote,
  },
  materials: {
    eyebrow: "Материалы",
    title: "Состояние библиотеки",
    body: "Здесь важны готовность материалов и удобство навигации по ним.",
    icon: BookOpenText,
  },
};

export function SourcePanel({ activeSection, status, lastRun }: SourcePanelProps) {
  const coverageCards = buildCoverageCards(lastRun);
  // A run happened but nothing backed it — distinct from "no run yet" so the
  // panel can say "не нашлось" instead of "появится после генерации".
  const ranWithoutCoverage = Boolean(lastRun) && coverageCards.length === 0;
  const copy = panelCopy[activeSection];
  const Icon = copy.icon;

  if (activeSection === "summary") {
    return (
      <aside className="source-panel">
        <div className="mb-5">
          <div className="text-sm font-semibold accent">{copy.eyebrow}</div>
          <h2 className="mt-1 text-lg font-bold">{copy.title}</h2>
          <p className="mt-2 text-sm leading-6 muted">{copy.body}</p>
        </div>

        <div className="rounded-xl border border-[var(--line)] bg-[rgba(255,255,255,0.03)] p-4">
          <div className="flex items-center gap-2">
            <Icon className="text-[var(--source)]" size={16} />
            <div className="text-sm font-semibold">Последняя тема</div>
          </div>
          <div className="mt-3 text-sm font-medium text-white">
            {lastRun?.trace?.request?.topic || "Пока нет последнего запуска"}
          </div>
          <div className="mt-2 text-sm muted">
            {coverageCards.length > 0
              ? `Есть ${coverageCards.length} ключевых блока покрытия, которые можно быстро проверить глазами.`
              : ranWithoutCoverage
                ? "По последней теме подтверждающих фрагментов не нашлось. Стоит уточнить тему или выбрать другой материал."
                : "После первой генерации здесь появятся разделы и фрагменты, которые поддержали конспект."}
          </div>
        </div>

        <div className="mt-3 space-y-3">
          {coverageCards.length > 0 ? (
            coverageCards.map((item) => (
              <div key={item.title} className="rounded-xl border border-[var(--line)] bg-[rgba(255,255,255,0.03)] p-4">
                <div className="text-sm font-semibold text-white">{item.title}</div>
                <div className="mt-1 text-xs muted">{item.meta}</div>
                <p className="mt-3 text-sm leading-6 text-slate-200">{item.detail}</p>
              </div>
            ))
          ) : (
            <div className="rounded-xl border border-dashed border-[var(--line)] bg-[rgba(255,255,255,0.03)] p-4 text-sm muted">
              {ranWithoutCoverage
                ? "По этой теме фрагменты не найдены — похоже, материал не относится к запросу."
                : "Этот блок станет полезным сразу после первого успешного конспекта."}
            </div>
          )}
        </div>
      </aside>
    );
  }

  return (
    <aside className="source-panel">
      <div className="mb-5">
        <div className="text-sm font-semibold accent">{copy.eyebrow}</div>
        <h2 className="mt-1 text-lg font-bold">{copy.title}</h2>
        <p className="mt-2 text-sm leading-6 muted">{copy.body}</p>
      </div>

      <div className="space-y-3">
        {activeSection === "assistant" ? (
          <>
            <div className="rounded-xl border border-[var(--line)] bg-[rgba(255,255,255,0.03)] p-4">
              <div className="text-sm font-semibold text-white">Лучший сценарий</div>
              <p className="mt-3 text-sm leading-6 muted">
                Сначала попросить объяснить тему, потом сузить вопрос, а затем при желании добить ответ цитатами.
              </p>
            </div>
            <div className="rounded-xl border border-[var(--line)] bg-[rgba(255,255,255,0.03)] p-4">
              <div className="text-sm font-semibold text-white">Что полезно после ответа</div>
              <p className="mt-3 text-sm leading-6 muted">
                Обычно следующий сильный ход: “упрости”, “сравни”, “дай только главное” или “покажи подтверждение”.
              </p>
            </div>
          </>
        ) : (
          <div className="rounded-xl border border-[var(--line)] bg-[rgba(255,255,255,0.03)] p-4">
            <div className="text-sm font-semibold text-white">Материалов в базе</div>
            <div className="mt-3 text-2xl font-bold text-white">{status.total_books}</div>
            <p className="mt-2 text-sm leading-6 muted">Это общее число источников, которые уже доступны системе.</p>
          </div>
        )}
      </div>
    </aside>
  );
}
