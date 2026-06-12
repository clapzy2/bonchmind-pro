"use client";

import { AlertTriangle, BadgeCheck } from "lucide-react";

import type { ChatResponse, SummaryResponse, TraceChunkGroup } from "@/lib/api";

/**
 * Compact, collapsible diagnostics for the working screens (Stage 7d).
 * Replaces the separate "Проверка качества" tab: the human-readable
 * strengths/warnings copy moved here from the deleted quality-workspace,
 * and the raw diagnostics string stays available in a <pre> for dev use.
 */

type QualitySignals = {
  strengths: string[];
  warnings: string[];
};

function isChunkGroupArray(value: unknown): value is TraceChunkGroup[] {
  return Array.isArray(value) && value.length > 0 && typeof value[0] === "object" && value[0] !== null && "chunks" in value[0];
}

/** Quality narrative for a summary run — ported from quality-workspace. */
export function buildSummaryQualitySignals(result: SummaryResponse | null): QualitySignals {
  const rawGroups = result?.trace?.chunks?.planned_chunk_groups;
  const groups = isChunkGroupArray(rawGroups) ? rawGroups : [];
  const llmCalls = result?.trace?.llm_calls?.length ?? 0;
  const elapsed = typeof result?.trace?.elapsed_sec === "number" ? result.trace.elapsed_sec : 0;
  const fragmentCount = groups.reduce((total, group) => total + group.chunks.length, 0);
  const emptyGroups = groups.filter((group) => group.chunks.length === 0).length;
  const groupsWithSingleChunk = groups.filter((group) => group.chunks.length === 1).length;

  const strengths: string[] = [];
  const warnings: string[] = [];

  if (fragmentCount >= 12) {
    strengths.push("Ответ опирается на плотную подборку фрагментов, а не на один случайный кусок текста.");
  } else if (fragmentCount > 0) {
    warnings.push("Фрагментов немного: ответ уже рабочий, но запас подтверждений пока небольшой.");
  }

  if (groups.length >= 4 && emptyGroups === 0) {
    strengths.push("Пункты плана покрыты равномерно: система не провалилась в один раздел.");
  }

  if (groupsWithSingleChunk >= 2) {
    warnings.push("Часть пунктов держится всего на одном фрагменте. Такие места стоит проверять внимательнее.");
  }

  if (llmCalls === 1) {
    strengths.push("Синтез выполнен одним вызовом модели без лишней каскадной сложности.");
  } else if (llmCalls > 2) {
    warnings.push("Модель дергалась несколько раз. Это не ошибка, но добавляет вариативность результата.");
  }

  if (elapsed >= 45) {
    warnings.push("Запуск был долгим. Для пользователя это уже чувствительно.");
  }

  if (result && result.trace?.status !== "ok") {
    warnings.push("Запуск завершился неидеально — стоит заглянуть в сырую диагностику ниже.");
  }

  return { strengths, warnings };
}

/** Quality narrative for a chat answer — intentionally simpler. */
export function buildChatQualitySignals(response: ChatResponse | null): QualitySignals {
  const sourcesCount = response?.sources?.length ?? 0;

  const strengths: string[] = [];
  const warnings: string[] = [];

  if (sourcesCount >= 3) {
    strengths.push("Ответ опирается на несколько подтверждающих фрагментов из материалов.");
  } else if (sourcesCount > 0) {
    warnings.push("Подтверждающих фрагментов немного: ответ рабочий, но лучше свериться с материалом.");
  } else {
    warnings.push("Ответ не опирается на фрагменты из базы — возможно, информации нет в материалах.");
  }

  if (response && response.trace?.status !== "ok") {
    warnings.push("Ответ получен с предупреждением — детали в сырой диагностике ниже.");
  }

  return { strengths, warnings };
}

type RunDiagnosticsProps = {
  title: string;
  /** Short facts shown as chips, e.g. "Статус: ok", "Источников: 3". */
  meta?: string[];
  strengths: string[];
  warnings: string[];
  /** Raw backend diagnostics string; rendered in a <pre> for dev cases. */
  diagnostics: string;
};

export function RunDiagnostics({ title, meta, strengths, warnings, diagnostics }: RunDiagnosticsProps) {
  return (
    <details className="bm-surface rounded-xl p-4 shadow-soft">
      <summary className="cursor-pointer text-sm font-semibold text-white">{title}</summary>

      <div className="mt-4 space-y-4">
        {meta?.length ? (
          <div className="flex flex-wrap gap-2">
            {meta.map((item) => (
              <span
                key={item}
                className="rounded-lg border border-white/10 bg-[#0d1117] px-3 py-1.5 text-xs font-semibold text-slate-200"
              >
                {item}
              </span>
            ))}
          </div>
        ) : null}

        {strengths.length > 0 || warnings.length > 0 ? (
          <div className="grid gap-3 md:grid-cols-2">
            {strengths.length > 0 ? (
              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
                <div className="flex items-center gap-2 text-emerald-100">
                  <BadgeCheck className="h-4 w-4" />
                  <span className="text-sm font-semibold">Что выглядит хорошо</span>
                </div>
                <div className="mt-3 space-y-2 text-sm leading-6 text-emerald-50/90">
                  {strengths.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </div>
              </div>
            ) : null}

            {warnings.length > 0 ? (
              <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
                <div className="flex items-center gap-2 text-amber-100">
                  <AlertTriangle className="h-4 w-4" />
                  <span className="text-sm font-semibold">Что стоит проверить</span>
                </div>
                <div className="mt-3 space-y-2 text-sm leading-6 text-amber-50/90">
                  {warnings.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

        <pre className="max-h-[320px] overflow-auto whitespace-pre-wrap rounded-xl border border-white/10 bg-[#0d1117] p-4 text-xs leading-6 text-slate-300 assistant-scroll">
          {diagnostics || "Сырая диагностика недоступна для этого запуска."}
        </pre>
      </div>
    </details>
  );
}
