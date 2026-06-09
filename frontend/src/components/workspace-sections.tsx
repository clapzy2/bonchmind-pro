"use client";

import { BookMarked, CircleCheckBig, MessageSquareQuote, Settings2, Sparkles } from "lucide-react";

import type { MaterialInfo, SummaryResponse, SystemStatus } from "@/lib/api";

export type WorkspaceSection = "summary" | "assistant" | "materials" | "quality" | "settings";

type WorkspaceSectionViewProps = {
  activeSection: Exclude<WorkspaceSection, "summary">;
  lastRun: SummaryResponse | null;
  materials: MaterialInfo[];
  status: SystemStatus;
};

const sectionCopy = {
  assistant: {
    eyebrow: "Ассистент",
    title: "Ассистент по материалам",
    description: "Живой диалог по материалам с опорой на реальные фрагменты базы.",
  },
  materials: {
    eyebrow: "Библиотека",
    title: "Материалы и структура",
    description: "Список материалов, структура и готовность базы к работе.",
  },
  quality: {
    eyebrow: "Контроль качества",
    title: "Надежность и проверка",
    description: "Покрытие ответа, слабые места и понятная диагностика запуска.",
  },
  settings: {
    eyebrow: "Настройки",
    title: "Настройки продукта",
    description: "Модели, режимы и параметры станции без лишнего технического шума.",
  },
} as const;

export function WorkspaceSectionView({
  activeSection,
  lastRun,
  materials,
  status,
}: WorkspaceSectionViewProps) {
  const copy = sectionCopy[activeSection];
  const generated = lastRun?.trace?.status === "ok";

  return (
    <div className="space-y-6">
      <section className="bm-surface rounded-xl p-7 shadow-soft">
        <div className="max-w-4xl">
          <p className="text-sm font-semibold text-brand">{copy.eyebrow}</p>
          <h1 className="mt-3 text-4xl font-bold tracking-tight text-white">{copy.title}</h1>
          <p className="mt-4 text-base leading-8 text-muted">{copy.description}</p>
        </div>

        <div className="mt-8 grid gap-4 lg:grid-cols-3">
          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="flex items-center gap-2 text-white">
              <Sparkles className="h-4 w-4 text-brand" />
              <span className="text-sm font-semibold">Сейчас в продукте</span>
            </div>
            <p className="mt-3 text-sm leading-7 text-muted">
              Конспекты уже работают в новом интерфейсе вместе с покрытием, диагностикой и экспортом.
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="flex items-center gap-2 text-white">
              <BookMarked className="h-4 w-4 text-[var(--source)]" />
              <span className="text-sm font-semibold">Библиотека</span>
            </div>
            <p className="mt-3 text-sm leading-7 text-muted">
              В базе уже {status.total_books} книг и {status.total_chunks} фрагментов. Это база для остальных модулей.
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="flex items-center gap-2 text-white">
              <CircleCheckBig className="h-4 w-4 text-emerald-400" />
              <span className="text-sm font-semibold">Последний запуск</span>
            </div>
            <p className="mt-3 text-sm leading-7 text-muted">
              {generated
                ? "Последняя генерация завершилась успешно и уже опирается на живые данные."
                : "После следующей успешной генерации здесь появится сводка по реальному запуску."}
            </p>
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="bm-surface rounded-xl p-6 shadow-soft">
          <div className="flex items-center gap-3">
            {activeSection === "assistant" ? (
              <MessageSquareQuote className="h-5 w-5 text-brand" />
            ) : activeSection === "materials" ? (
              <BookMarked className="h-5 w-5 text-brand" />
            ) : activeSection === "quality" ? (
              <CircleCheckBig className="h-5 w-5 text-brand" />
            ) : (
              <Settings2 className="h-5 w-5 text-brand" />
            )}
            <h2 className="text-lg font-bold text-white">Что увидит пользователь</h2>
          </div>
          <div className="mt-5 space-y-3 text-sm leading-7 text-muted">
            {activeSection === "assistant" ? (
              <>
                <p>Диалог с понятной ссылкой на источник, а не просто ответ нейросети.</p>
                <p>Быстрые режимы: объяснить, кратко, подробно или цитатами.</p>
                <p>Уверенность ответа и ближайшие подтверждающие фрагменты без перегруза техничкой.</p>
              </>
            ) : activeSection === "materials" ? (
              <>
                <p>Список книг, разделов и статуса индексации в одной библиотеке.</p>
                <p>Быстро видно, что уже готово к поиску, а что еще слабое.</p>
                <p>Загрузка и обновление материалов без ощущения админки для разработчика.</p>
              </>
            ) : activeSection === "quality" ? (
              <>
                <p>Понятный ответ на вопрос: почему система ответила именно так.</p>
                <p>Разделы, фрагменты и слабые места каждого запуска.</p>
                <p>Быстрый путь от сомнения к проверке без чтения сырого trace.</p>
              </>
            ) : (
              <>
                <p>Минимум сложных слов и максимум полезных переключателей.</p>
                <p>Прозрачное управление режимами модели и стилем генерации.</p>
                <p>Раздел, который помогает настроить станцию под себя.</p>
              </>
            )}
          </div>
        </div>

        <div className="bm-surface rounded-xl p-6 shadow-soft">
          <div className="flex items-center gap-3">
            <Sparkles className="h-5 w-5 text-brand" />
            <h2 className="text-lg font-bold text-white">Ближайшая сборка</h2>
          </div>
          <div className="mt-5 grid gap-3">
            {activeSection === "assistant" ? (
              <>
                <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4 text-sm text-muted">
                  Новый чатовый экран с историей диалога и быстрыми режимами вопроса.
                </div>
                <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4 text-sm text-muted">
                  Подключение существующего RAG-ядра из Gradio в новый frontend.
                </div>
                <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4 text-sm text-muted">
                  Блок “почему я так ответил” рядом с диалогом.
                </div>
              </>
            ) : activeSection === "materials" ? (
              <>
                <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4 text-sm text-muted">
                  Реальный список материалов с поиском, статусами и разделами.
                </div>
                <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4 text-sm text-muted">
                  Загрузка файлов из нового интерфейса, без возврата в старый Gradio.
                </div>
                <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4 text-sm text-muted">
                  Просмотр проблемных материалов и переиндексация по одному клику.
                </div>
              </>
            ) : activeSection === "quality" ? (
              <>
                <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4 text-sm text-muted">
                  Отдельный экран разбора покрытия по пунктам плана и section match.
                </div>
                <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4 text-sm text-muted">
                  Примеры неудачных запусков и ручная проверка качества ответов.
                </div>
                <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4 text-sm text-muted">
                  Удобный dev-режим для тебя и будущего тестировщика.
                </div>
              </>
            ) : (
              <>
                <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4 text-sm text-muted">
                  Настройки моделей и режимов генерации в одном месте.
                </div>
                <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4 text-sm text-muted">
                  Системная диагностика: health, модели, chunk size, reranker.
                </div>
                <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4 text-sm text-muted">
                  Продуктовый слой настроек без ощущения “техпанели из лаборатории”.
                </div>
              </>
            )}
          </div>
        </div>
      </section>

      <section className="bm-surface rounded-xl p-6 shadow-soft">
        <h2 className="text-lg font-bold text-white">Текущая опора системы</h2>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="text-xs uppercase tracking-[0.2em] text-muted">Материалов</div>
            <div className="mt-3 text-3xl font-bold text-white">{materials.length}</div>
            <div className="mt-2 text-sm text-muted">видно в новой библиотеке уже сейчас</div>
          </div>
          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="text-xs uppercase tracking-[0.2em] text-muted">Фрагментов</div>
            <div className="mt-3 text-3xl font-bold text-white">{status.total_chunks}</div>
            <div className="mt-2 text-sm text-muted">готовы для retrieval и тематических конспектов</div>
          </div>
          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="text-xs uppercase tracking-[0.2em] text-muted">Последняя тема</div>
            <div className="mt-3 text-lg font-bold text-white">
              {lastRun?.trace?.request?.topic || "ожидает первый запуск"}
            </div>
            <div className="mt-2 text-sm text-muted">это позволяет остальным разделам быть живыми, а не статичными</div>
          </div>
        </div>
      </section>
    </div>
  );
}
