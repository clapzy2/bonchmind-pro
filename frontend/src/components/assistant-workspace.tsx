"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bot, Loader2, MessageSquareQuote, Send, Sparkles } from "lucide-react";

import type { ChatMessage, ChatResponse, MaterialInfo } from "@/lib/api";
import { sendChatMessage } from "@/lib/api";
import { MaterialPicker, SegmentedControl } from "@/components/workspace-controls";
import { handleAuthError } from "@/lib/handle-auth-error";

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
  const router = useRouter();
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
        // Restoring a saved preference once the material list is available is an
        // external-system sync (localStorage), not derived render state.
        // eslint-disable-next-line react-hooks/set-state-in-effect
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
      if (handleAuthError(error, router)) return;
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

  return (
    <div className="space-y-6">
      <section className="bm-surface rounded-xl p-6 shadow-soft">
        <div className="max-w-3xl">
          <h1 className="text-2xl font-bold tracking-tight text-white">Ассистент</h1>
          <p className="mt-2 text-sm leading-6 text-muted">
            Задавайте вопросы по своим материалам. Уточняйте короткими follow-up — так ответы заметно сильнее.
          </p>
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

      <section className="space-y-6">
        <div className="bm-surface flex min-h-[72vh] flex-col rounded-xl p-6 shadow-soft">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <MessageSquareQuote className="h-5 w-5 text-brand" />
              <h2 className="text-lg font-bold text-white">Диалог</h2>
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

        {lastResponse?.sources?.length ? (
          <details className="bm-surface rounded-xl p-4 shadow-soft">
            <summary className="cursor-pointer text-sm font-semibold text-white">
              Источники ответа · {lastResponse.sources.length}
            </summary>
            <div className="mt-4 space-y-2">
              {lastResponse.sources.map((source, index) => (
                <div
                  key={`${source.label}-${index}`}
                  className="flex items-start justify-between gap-3 rounded-lg border border-white/10 bg-[#0f1319] px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-white">{source.label}</div>
                    <div className="mt-1 truncate text-xs text-muted">
                      {source.source_file || "Источник без имени"}
                    </div>
                  </div>
                  <div className="shrink-0 rounded-full bg-white/5 px-2 py-0.5 text-xs font-semibold text-slate-200">
                    {source.score.toFixed(2)}
                  </div>
                </div>
              ))}
            </div>
          </details>
        ) : null}
      </section>
    </div>
  );
}
