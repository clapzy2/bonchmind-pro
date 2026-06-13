"use client";

import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bot, Loader2, MessageSquareQuote, Paperclip, Send, Sparkles } from "lucide-react";

import type { ChatMessage, ChatResponse, MaterialInfo } from "@/lib/api";
import { sendChatMessage } from "@/lib/api";
import { MaterialPicker, SegmentedControl } from "@/components/workspace-controls";
import { handleAuthError } from "@/lib/handle-auth-error";
import { Markdown } from "@/components/markdown";
import { UploadInline } from "@/components/upload-inline";
import { useMaterialOperations } from "@/lib/use-material-operations";
import { useAuth } from "@/lib/auth-context";

const UPLOAD_ACCEPT = ".pdf,.txt,.epub,.docx,.md,.fb2,.zip,.html,.htm";

type AssistantWorkspaceProps = {
  materials: MaterialInfo[];
  onLibraryChange?: () => Promise<void> | void;
};

const answerModes = ["Обычный", "Кратко", "Только цитаты"];
const ASSISTANT_PREFERENCES_KEY = "bonchmind-assistant-preferences";
// Chat history survives F5. sessionStorage + owner-id stamp for the same
// reason as the summary: replies and sources are workspace-scoped content
// that must never surface for another account on a shared browser.
const SESSION_KEY = "bonchmind-assistant-session";
const quickPrompts = [
  "Объясни простыми словами ключевую идею.",
  "Сделай краткий ответ в 3-4 пунктах.",
  "Приведи подтверждающие цитаты из материала.",
];

type Notice = {
  tone: "success" | "warning" | "info";
  text: string;
};

export function AssistantWorkspace({ materials, onLibraryChange }: AssistantWorkspaceProps) {
  const router = useRouter();
  const { user } = useAuth();
  const materialOptions = useMemo(() => ["Все материалы", ...materials.map((material) => material.name)], [materials]);

  const [selectedFile, setSelectedFile] = useState(materialOptions[0] ?? "Все материалы");
  const [answerMode, setAnswerMode] = useState("Обычный");
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [lastResponse, setLastResponse] = useState<ChatResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const historyViewportRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const upload = useMaterialOperations({
    onSync: async () => {
      await onLibraryChange?.();
    },
  });

  function handleUploadChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || upload.isRunning) {
      return;
    }
    // Auto-select the freshly uploaded file so the next question targets it.
    void upload.uploadFile(file, (materialName) => setSelectedFile(materialName));
  }

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

  // Restore the chat after F5, gated to the current user so one account never
  // sees another's conversation on a shared browser.
  useEffect(() => {
    if (!user?.id) {
      return;
    }
    const raw = window.sessionStorage.getItem(SESSION_KEY);
    if (!raw) {
      return;
    }
    try {
      const parsed = JSON.parse(raw) as {
        userId?: string;
        history?: ChatMessage[];
        lastResponse?: ChatResponse | null;
      };
      if (parsed.userId === user.id && Array.isArray(parsed.history)) {
        // External-system (sessionStorage) restore, not derived render state.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setHistory(parsed.history);
        if (parsed.lastResponse) {
          setLastResponse(parsed.lastResponse);
        }
      } else if (parsed.userId !== user.id) {
        window.sessionStorage.removeItem(SESSION_KEY);
      }
    } catch {
      window.sessionStorage.removeItem(SESSION_KEY);
    }
  }, [user?.id]);

  // Persist the conversation (stamped with the owner id) so it survives F5.
  useEffect(() => {
    if (!user?.id || history.length === 0) {
      return;
    }
    window.sessionStorage.setItem(
      SESSION_KEY,
      JSON.stringify({ userId: user.id, history, lastResponse }),
    );
  }, [history, lastResponse, user?.id]);

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
            Задайте вопрос по загруженным материалам — ассистент ответит с опорой на источники.
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
            label="Стиль ответа"
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
                  {item.role === "user" ? (
                    <div className="whitespace-pre-wrap text-sm leading-7 text-slate-200">{item.content}</div>
                  ) : (
                    <Markdown>{item.content}</Markdown>
                  )}
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
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept={UPLOAD_ACCEPT}
                onChange={handleUploadChange}
              />
              <button
                className="bm-button-secondary flex h-12 w-12 items-center justify-center disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                disabled={upload.isRunning}
                onClick={() => fileInputRef.current?.click()}
                aria-label="Загрузить материал"
                title="Загрузить материал"
              >
                {upload.activeOperation === "upload" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Paperclip className="h-4 w-4" />
                )}
              </button>
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
                Скрепка — чтобы загрузить новый материал прямо отсюда.
              </p>
            </div>

            <UploadInline progress={upload.progress} notice={upload.notice} onCancel={upload.cancel} cancelling={upload.cancelling} />

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
      </section>
    </div>
  );
}
