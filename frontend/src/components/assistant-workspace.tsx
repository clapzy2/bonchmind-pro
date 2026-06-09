"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUpRight, BadgeCheck, BookOpenText, Bot, Loader2, MessageSquareQuote, Send, Sparkles } from "lucide-react";

import type { ChatMessage, ChatResponse, MaterialInfo } from "@/lib/api";
import { sendChatMessage } from "@/lib/api";
import { MaterialPicker, SegmentedControl } from "@/components/workspace-controls";

type AssistantWorkspaceProps = {
  materials: MaterialInfo[];
};

const answerModes = ["Обычный", "Кратко", "Подробно", "Только цитаты"];
const ASSISTANT_PREFERENCES_KEY = "bonchmind-assistant-preferences";
const quickPrompts = [
  "Объясни простыми словами ключевую идею раздела.",
  "Сделай краткий ответ по теме в 3-4 пунктах.",
  "Приведи только подтверждающие цитаты из материала.",
  "Сравни два важных понятия из текущего материала.",
];
const studyScenarios = [
  {
    title: "Понять тему",
    description: "Когда нужно быстро врубиться в смысл и не утонуть в формулировках учебника.",
    prompt: "Объясни тему простыми словами, потом выдели 3 ключевые идеи и 1 типичную ошибку в понимании.",
  },
  {
    title: "Повторить перед занятием",
    description: "Сжать материал до опорных пунктов и быстро пробежать глазами перед парой или созвоном.",
    prompt: "Сделай краткое повторение темы: 5 опорных пунктов, 3 термина и 1 короткий вывод.",
  },
  {
    title: "Самопроверка",
    description: "Не оценивать вместо преподавателя, а помочь самому понять, что ты реально помнишь.",
    prompt:
      "Сделай режим самопроверки по теме: задай 5 вопросов по материалу по одному, не ставь оценку, а после каждого моего ответа коротко скажи, чего не хватает и на что обратить внимание.",
  },
  {
    title: "Подготовка по цитатам",
    description: "Когда важно держаться строго за текст и не подмешивать лишние интерпретации.",
    prompt: "Собери по теме ключевые цитаты и коротко подпиши, какую мысль каждая из них подтверждает.",
  },
];

type Notice = {
  tone: "success" | "warning" | "info";
  text: string;
};

export function AssistantWorkspace({ materials }: AssistantWorkspaceProps) {
  const materialOptions = useMemo(() => ["Все материалы", ...materials.map((material) => material.name)], [materials]);

  const [selectedFile, setSelectedFile] = useState(materialOptions[0] ?? "Все материалы");
  const [answerMode, setAnswerMode] = useState("Обычный");
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [lastResponse, setLastResponse] = useState<ChatResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const historyViewportRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const raw = window.localStorage.getItem(ASSISTANT_PREFERENCES_KEY);
    if (!raw) {
      return;
    }

    try {
      const parsed = JSON.parse(raw) as {
        selectedFile?: string;
        answerMode?: string;
      };

      if (
        parsed.selectedFile &&
        (parsed.selectedFile === "Все материалы" || materialOptions.includes(parsed.selectedFile))
      ) {
        setSelectedFile(parsed.selectedFile);
      }
      if (parsed.answerMode && answerModes.includes(parsed.answerMode)) {
        setAnswerMode(parsed.answerMode);
      }
    } catch {
      window.localStorage.removeItem(ASSISTANT_PREFERENCES_KEY);
    }
  }, [materialOptions]);

  useEffect(() => {
    window.localStorage.setItem(
      ASSISTANT_PREFERENCES_KEY,
      JSON.stringify({ selectedFile, answerMode }),
    );
  }, [selectedFile, answerMode]);

  useEffect(() => {
    const viewport = historyViewportRef.current;
    if (!viewport) {
      return;
    }

    viewport.scrollTo({
      top: viewport.scrollHeight,
      behavior: "smooth",
    });
  }, [history, isLoading]);

  async function handleSend() {
    const normalizedMessage = message.trim();
    if (!normalizedMessage || isLoading) {
      return;
    }

    setIsLoading(true);
    setNotice({
      tone: "info",
      text: "Ассистент ищет релевантные фрагменты и собирает ответ.",
    });

    try {
      const response = await sendChatMessage({
        message: normalizedMessage,
        history,
        selected_file: selectedFile,
        answer_mode: answerMode,
      });

      setHistory(response.history);
      setLastResponse(response);
      setMessage("");
      setNotice({
        tone: response.trace?.status === "ok" ? "success" : "warning",
        text:
          response.trace?.status === "ok"
            ? "Ответ готов. Можно сверить источники и задать уточняющий вопрос."
            : "Ответ получен с предупреждением. Лучше проверить источники и диагностику.",
      });
    } catch (error) {
      setNotice({
        tone: "warning",
        text:
          error instanceof Error
            ? `Не удалось получить ответ: ${error.message}`
            : "Не удалось получить ответ. Проверьте backend.",
      });
    } finally {
      setIsLoading(false);
    }
  }

  const visibleHistory = history.length > 0 ? history : [
    {
      role: "assistant" as const,
      content:
        "Задайте вопрос по загруженным материалам. Новый интерфейс уже использует то же ядро поиска и ответа, что раньше работало в Gradio.",
    },
  ];

  const confidenceTone =
    lastResponse?.confidence_label === "high"
      ? "bg-emerald-500/12 text-emerald-200"
      : lastResponse?.confidence_label === "medium"
        ? "bg-cyan-500/12 text-cyan-200"
        : lastResponse?.confidence_label === "system"
          ? "bg-white/8 text-slate-200"
          : "bg-amber-500/12 text-amber-200";

  return (
    <div className="space-y-6">
      <section className="bm-surface rounded-xl p-6 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold text-brand">Ассистент</p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight text-white">Разобрать материал в диалоге</h1>
            <p className="mt-3 text-base leading-7 text-muted">
              Здесь важен не один длинный запрос, а живая серия уточнений. Спросили, сузили, перепроверили цитатами, пошли дальше.
            </p>
          </div>
        </div>

        <div className="mt-6 grid gap-5 xl:grid-cols-[1.12fr_0.88fr]">
          <MaterialPicker
            label="Материал"
            materials={materials}
            value={selectedFile}
            onChange={setSelectedFile}
          />
          <SegmentedControl
            label="Тип ответа"
            options={answerModes}
            value={answerMode}
            onChange={setAnswerMode}
          />
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          {quickPrompts.map((prompt) => (
            <button
              key={prompt}
              className="rounded-full border border-white/10 bg-[#0d1117] px-4 py-2 text-sm text-slate-200 transition hover:border-white/20 hover:bg-[#131923]"
              type="button"
              onClick={() => setMessage(prompt)}
            >
              {prompt}
            </button>
          ))}
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.12fr_0.88fr]">
        <div className="bm-surface flex min-h-[82vh] flex-col rounded-xl p-6 shadow-soft">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <MessageSquareQuote className="h-5 w-5 text-brand" />
                <h2 className="text-lg font-bold text-white">Диалог</h2>
              </div>
              <p className="mt-2 text-sm leading-6 text-muted">
                Ведите тему короткими follow-up вопросами. Так ассистент держит контекст и отвечает ощутимо сильнее.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <div className="rounded-full border border-white/10 bg-[#0f1319] px-3 py-1.5 text-xs font-semibold text-slate-200">
                {selectedFile}
              </div>
              <div className="rounded-full border border-white/10 bg-[#0f1319] px-3 py-1.5 text-xs font-semibold text-slate-200">
                {answerMode}
              </div>
            </div>
          </div>

          <div ref={historyViewportRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-2 assistant-scroll">
            {history.length === 0 ? (
              <div className="grid gap-3 lg:grid-cols-2">
                {studyScenarios.map((item) => (
                  <button
                    key={item.title}
                    type="button"
                    onClick={() => setMessage(item.prompt)}
                    className="rounded-xl border border-white/10 bg-[#0f1319] p-4 text-left transition hover:border-white/20 hover:bg-[#131923] hover:shadow-[0_12px_24px_rgba(0,0,0,0.12)]"
                  >
                    <div className="text-sm font-semibold text-white">{item.title}</div>
                    <div className="mt-3 text-sm leading-6 text-muted">{item.description}</div>
                  </button>
                ))}
              </div>
            ) : null}

            {visibleHistory.map((item, index) => (
              <div
                key={`${item.role}-${index}`}
                className={`flex ${item.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                className={`max-w-[88%] rounded-2xl border p-4 ${
                  item.role === "user"
                    ? "border-brand/20 bg-[rgba(240,90,26,0.08)]"
                    : "border-white/10 bg-[#0d1117]"
                }`}
                >
                  <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-white">
                    {item.role === "user" ? (
                      <>
                        <Sparkles className="h-4 w-4 text-brand" />
                        Вы
                      </>
                    ) : (
                      <>
                        <Bot className="h-4 w-4 text-[var(--source)]" />
                        BonchMind
                      </>
                    )}
                  </div>
                  <div className="whitespace-pre-wrap text-sm leading-7 text-slate-200">{item.content}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="bm-chat-composer mt-6 border-t border-white/10 pt-5">
            <label className="block space-y-2">
              <span className="text-sm font-semibold text-white">Новый вопрос</span>
              <textarea
                className="bm-textarea min-h-28 w-full text-white"
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                placeholder="Например: Объясни простыми словами, что такое Bluetooth, и на чем основан стандарт."
              />
            </label>

            <div className="mt-4 flex flex-wrap items-center gap-4">
              <button
                className="bm-button-primary h-12 px-6 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                disabled={isLoading || !message.trim()}
                onClick={handleSend}
              >
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                {isLoading ? "Отвечаю..." : "Отправить"}
              </button>
              <p className="text-sm text-muted">
                Короткие уточнения вроде “подробнее” продолжают предыдущий контекст.
              </p>
            </div>

            {notice ? (
              <div
                className={`mt-4 rounded-md px-4 py-3 text-sm ${
                  notice.tone === "success"
                    ? "border border-emerald-500/30 bg-emerald-500/10 text-emerald-100"
                    : notice.tone === "warning"
                      ? "border border-amber-500/30 bg-amber-500/10 text-amber-100"
                      : "border border-cyan-500/30 bg-cyan-500/10 text-cyan-100"
                }`}
              >
                {notice.text}
              </div>
            ) : null}
          </div>
        </div>

        <div className="space-y-6">
          <section className="bm-surface rounded-xl p-6 shadow-soft">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-bold text-white">Смысл последнего ответа</h2>
                <p className="mt-2 text-sm leading-7 text-muted">
                  Короткий итог, уверенность и удобные следующие шаги.
                </p>
              </div>
              <div className={`rounded-full px-3 py-1.5 text-xs font-semibold ${confidenceTone}`}>
                {lastResponse?.confidence_label || "idle"}
              </div>
            </div>

            <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <BadgeCheck className="h-4 w-4 text-brand" />
                Короткий итог
              </div>
              <p className="mt-3 text-sm leading-7 text-slate-200">
                {lastResponse?.summary || "После первого ответа здесь появится короткий, человеческий итог без лишней воды."}
              </p>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-white">
                  <BookOpenText className="h-4 w-4 text-brand" />
                  Что понял бот
                </div>
                <p className="mt-3 text-sm leading-7 text-muted">
                  {message.trim()
                    ? "Последний запрос уже в работе или готов к отправке."
                    : "Ассистент особенно хорош, когда вы ведете тему короткими уточнениями."}
                </p>
              </div>
              <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-white">
                  <ArrowUpRight className="h-4 w-4 text-brand" />
                  Следующий ход
                </div>
                <p className="mt-3 text-sm leading-7 text-muted">
                  Обычно дальше полезно: упростить, сравнить или проверить цитатами.
                </p>
              </div>
            </div>

            <div className="mt-4">
              <div className="text-sm font-semibold text-white">Что спросить дальше</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {(lastResponse?.followup_suggestions?.length
                  ? lastResponse.followup_suggestions
                  : [
                      "Объясни это простыми словами.",
                      "Сделай краткий вывод по теме.",
                      "Покажи подтверждающие цитаты.",
                    ]).map((prompt) => (
                  <button
                    key={prompt}
                    className="rounded-full border border-white/10 bg-[#0d1117] px-4 py-2 text-sm text-slate-200 transition hover:border-white/20 hover:bg-[#131923]"
                    type="button"
                    onClick={() => setMessage(prompt)}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="bm-surface rounded-xl p-6 shadow-soft">
            <h2 className="text-lg font-bold text-white">Источники ответа</h2>
            <p className="mt-2 text-sm leading-7 text-muted">
              Ближайшие подтверждающие разделы для последнего ответа.
            </p>

            <div className="mt-5 max-h-[320px] space-y-3 overflow-y-auto pr-1 assistant-scroll">
              {lastResponse?.sources?.length ? (
                lastResponse.sources.map((source, index) => (
                  <div key={`${source.label}-${index}`} className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-white">{source.label}</div>
                        <div className="mt-1 text-xs text-muted">
                          {source.source_file || "Источник без имени"}
                        </div>
                      </div>
                      <div className="rounded-full bg-white/5 px-2.5 py-1 text-xs font-semibold text-slate-200">
                        {source.score.toFixed(3)}
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-xl border border-dashed border-white/10 bg-[#0f1319] p-4 text-sm muted">
                  После первого ответа здесь появятся подтверждающие разделы.
                </div>
              )}
            </div>
          </section>

        </div>
      </section>
    </div>
  );
}
