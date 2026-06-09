"use client";

import { AlertTriangle, BadgeCheck, Braces, Clock3, FileSearch, Layers3, Sparkles } from "lucide-react";

import type { SummaryResponse, TraceChunkGroup } from "@/lib/api";

type QualityWorkspaceProps = {
  lastRun: SummaryResponse | null;
};

function isChunkGroupArray(value: unknown): value is TraceChunkGroup[] {
  return Array.isArray(value) && value.length > 0 && typeof value[0] === "object" && value[0] !== null && "chunks" in value[0];
}

function getPlannedGroups(lastRun: SummaryResponse | null): TraceChunkGroup[] {
  const groups = lastRun?.trace?.chunks?.planned_chunk_groups;
  return isChunkGroupArray(groups) ? groups : [];
}

function buildQualitySignals(lastRun: SummaryResponse | null) {
  const groups = getPlannedGroups(lastRun);
  const llmCalls = lastRun?.trace?.llm_calls?.length ?? 0;
  const elapsed = typeof lastRun?.trace?.elapsed_sec === "number" ? lastRun.trace.elapsed_sec : 0;
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
    warnings.push("Запуск был долгим. Для пользователя это уже чувствительно и просит отдельной оптимизации.");
  } else if (elapsed > 0) {
    strengths.push("Время ответа пока укладывается в живой пользовательский сценарий.");
  }

  if (lastRun?.trace?.status !== "ok") {
    warnings.push("Последний запуск завершился неидеально. На такой ответ лучше смотреть вместе с диагностикой.");
  }

  return {
    groups,
    llmCalls,
    elapsed,
    fragmentCount,
    strengths,
    warnings,
  };
}

export function QualityWorkspace({ lastRun }: QualityWorkspaceProps) {
  const { groups, llmCalls, elapsed, fragmentCount, strengths, warnings } = buildQualitySignals(lastRun);
  const topic = lastRun?.trace?.request?.topic || "Пока нет последнего запуска";
  const status = lastRun?.trace?.status || "idle";
  const strategy = lastRun?.trace?.strategy || "не определена";

  return (
    <div className="space-y-6">
      <section className="bm-surface rounded-xl p-6 shadow-soft">
        <div className="max-w-4xl">
          <p className="text-sm font-semibold text-brand">Контроль качества</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-white">Проверка ответа и покрытия</h1>
          <p className="mt-3 text-base leading-7 text-muted">
            Срез по качеству ответа: опора на текст, слабые места и техническая сводка запуска.
          </p>
        </div>

        <div className="mt-8 grid gap-4 lg:grid-cols-4">
          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="flex items-center gap-2 text-white">
              <BadgeCheck className="h-4 w-4 text-emerald-400" />
              <span className="text-sm font-semibold">Статус</span>
            </div>
            <div className="mt-4 text-2xl font-bold text-white">{status}</div>
            <p className="mt-2 text-sm leading-6 text-muted">состояние последнего прогона</p>
          </div>

          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="flex items-center gap-2 text-white">
              <Layers3 className="h-4 w-4 text-[var(--source)]" />
              <span className="text-sm font-semibold">Фрагменты</span>
            </div>
            <div className="mt-4 text-2xl font-bold text-white">{fragmentCount}</div>
            <p className="mt-2 text-sm leading-6 text-muted">сколько опорных кусков реально было использовано</p>
          </div>

          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="flex items-center gap-2 text-white">
              <Braces className="h-4 w-4 text-brand" />
              <span className="text-sm font-semibold">LLM-вызовы</span>
            </div>
            <div className="mt-4 text-2xl font-bold text-white">{llmCalls}</div>
            <p className="mt-2 text-sm leading-6 text-muted">насколько сложной была генерация</p>
          </div>

          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="flex items-center gap-2 text-white">
              <Clock3 className="h-4 w-4 text-brand" />
              <span className="text-sm font-semibold">Время</span>
            </div>
            <div className="mt-4 text-2xl font-bold text-white">
              {elapsed > 0 ? `${Math.round(elapsed)} c` : "н/д"}
            </div>
            <p className="mt-2 text-sm leading-6 text-muted">ощущаемая задержка для пользователя</p>
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <section className="bm-surface rounded-xl p-6 shadow-soft">
          <div className="flex items-center gap-3">
            <Sparkles className="h-5 w-5 text-brand" />
            <h2 className="text-lg font-bold text-white">Краткий разбор качества</h2>
          </div>

          <div className="mt-5 rounded-xl border border-white/10 bg-[#0d1117] p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-white/35">Последняя тема</div>
            <div className="mt-3 text-lg font-bold text-white">{topic}</div>
            <div className="mt-2 text-sm text-muted">Стратегия: {strategy}</div>
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
              <div className="flex items-center gap-2 text-emerald-100">
                <BadgeCheck className="h-4 w-4" />
                <span className="text-sm font-semibold">Что выглядит хорошо</span>
              </div>
              <div className="mt-4 space-y-3 text-sm leading-6 text-emerald-50/90">
                {strengths.length > 0 ? (
                  strengths.map((item) => <p key={item}>{item}</p>)
                ) : (
                  <p>После следующего уверенного запуска здесь появятся сильные стороны ответа.</p>
                )}
              </div>
            </div>

            <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
              <div className="flex items-center gap-2 text-amber-100">
                <AlertTriangle className="h-4 w-4" />
                <span className="text-sm font-semibold">Что стоит проверить</span>
              </div>
              <div className="mt-4 space-y-3 text-sm leading-6 text-amber-50/90">
                {warnings.length > 0 ? (
                  warnings.map((item) => <p key={item}>{item}</p>)
                ) : (
                  <p>Пока явных предупреждений не видно. Это хороший знак для последнего ответа.</p>
                )}
              </div>
            </div>
          </div>
        </section>

        <section className="bm-surface rounded-xl p-6 shadow-soft">
          <div className="flex items-center gap-3">
            <FileSearch className="h-5 w-5 text-brand" />
            <h2 className="text-lg font-bold text-white">Покрытие по пунктам</h2>
          </div>
          <div className="mt-5 space-y-3">
            {groups.length > 0 ? (
              groups.map((group) => {
                const sections = Array.from(new Set(group.chunks.map((chunk) => chunk.section).filter(Boolean)));

                return (
                  <div key={group.item} className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-white">{group.item}</div>
                        <div className="mt-2 text-xs uppercase tracking-[0.16em] text-white/35">
                          {group.chunks.length} фрагм.
                        </div>
                      </div>
                      <div
                        className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                          group.chunks.length >= 3
                            ? "bg-emerald-500/12 text-emerald-200"
                            : group.chunks.length === 2
                              ? "bg-cyan-500/12 text-cyan-200"
                              : "bg-amber-500/12 text-amber-200"
                        }`}
                      >
                        {group.chunks.length >= 3 ? "Хорошо" : group.chunks.length === 2 ? "Нормально" : "Слабо"}
                      </div>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-muted">
                      {sections.slice(0, 3).join("; ") || "Точных разделов не видно"}
                    </p>
                  </div>
                );
              })
            ) : (
              <div className="rounded-xl border border-dashed border-white/10 bg-[#0f1319] p-5 text-sm leading-7 text-muted">
                Сначала сгенерируй конспект. После этого здесь появится понятный расклад по пунктам плана и их опоре на источники.
              </div>
            )}
          </div>
        </section>
      </div>

      <section className="bm-surface rounded-xl p-6 shadow-soft">
        <div className="flex items-center gap-3">
          <Braces className="h-5 w-5 text-brand" />
          <h2 className="text-lg font-bold text-white">Диагностика запуска</h2>
        </div>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-muted">
          Более технический слой для случаев, когда надо понять, где просел retrieval или почему модель повела себя нестабильно.
        </p>

        <pre className="mt-5 max-h-[420px] overflow-auto whitespace-pre-wrap rounded-xl border border-white/10 bg-[#0d1117] p-5 text-xs leading-6 text-slate-300 assistant-scroll">
          {lastRun?.diagnostics || "Диагностика появится после первого запуска из раздела Конспект."}
        </pre>
      </section>
    </div>
  );
}
