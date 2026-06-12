"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Download, Loader2, Play, Search } from "lucide-react";

import type { MaterialInfo, SummaryResponse, TraceChunkGroup } from "@/lib/api";
import { exportSummaryDocx, generateSummary } from "@/lib/api";
import { MaterialPicker, SegmentedControl } from "@/components/workspace-controls";
import { handleAuthError } from "@/lib/handle-auth-error";

type SummaryWorkspaceProps = {
  materials: MaterialInfo[];
  onResult?: (result: SummaryResponse) => void;
};

const summaryTypes = ["Краткий", "Средний", "Подробный"];
const PREFERENCES_KEY = "bonchmind-summary-preferences";

type Notice = {
  tone: "success" | "warning" | "info";
  text: string;
};

function isChunkGroupArray(value: unknown): value is TraceChunkGroup[] {
  return Array.isArray(value) && value.length > 0 && typeof value[0] === "object" && value[0] !== null && "chunks" in value[0];
}

export function SummaryWorkspace({ materials, onResult }: SummaryWorkspaceProps) {
  const router = useRouter();
  const materialOptions = useMemo(() => ["Все материалы", ...materials.map((material) => material.name)], [materials]);

  const [selectedFile, setSelectedFile] = useState(materialOptions[0] ?? "Все материалы");
  const [summaryType, setSummaryType] = useState("Средний");
  const [topic, setTopic] = useState("");
  const [result, setResult] = useState<SummaryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showSources, setShowSources] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);

  useEffect(() => {
    const raw = window.localStorage.getItem(PREFERENCES_KEY);
    if (!raw) {
      return;
    }

    try {
      const parsed = JSON.parse(raw) as {
        selectedFile?: string;
        summaryType?: string;
        topic?: string;
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
      if (parsed.summaryType && summaryTypes.includes(parsed.summaryType)) {
        setSummaryType(parsed.summaryType);
      }
      if (parsed.topic) {
        setTopic(parsed.topic);
      }
    } catch {
      window.localStorage.removeItem(PREFERENCES_KEY);
    }
  }, [materialOptions]);

  useEffect(() => {
    window.localStorage.setItem(
      PREFERENCES_KEY,
      JSON.stringify({
        selectedFile,
        summaryType,
        topic,
      }),
    );
  }, [selectedFile, summaryType, topic]);

  async function handleGenerate() {
    const normalizedTopic = topic.trim();
    if (!normalizedTopic || isLoading) {
      return;
    }

    setIsLoading(true);
    setShowSources(false);
    setExportError("");
    setNotice({
      tone: "info",
      text: "BonchMind собирает релевантные фрагменты и готовит конспект.",
    });
    try {
      const response = await generateSummary({
        selected_file: selectedFile,
        selected_section: "Все разделы",
        topic: normalizedTopic,
        summary_type: summaryType,
      });
      setResult(response);
      onResult?.(response);
      setNotice({
        tone: response.trace?.status === "ok" ? "success" : "warning",
        text:
          response.trace?.status === "ok"
            ? "Конспект готов. Можно проверить источники или экспортировать DOCX."
            : "Генерация завершилась с предупреждением. Проверьте диагностику и источники.",
      });
    } catch (err) {
      if (handleAuthError(err, router)) return;
      setNotice({
        tone: "warning",
        text: "Не удалось сгенерировать конспект. Проверьте backend и повторите попытку.",
      });
    } finally {
      setIsLoading(false);
    }
  }

  async function handleExport() {
    if (!result?.text || isExporting) {
      return;
    }

    setIsExporting(true);
    setExportError("");
    try {
      const blob = await exportSummaryDocx({
        text: result.text,
        selected_file: selectedFile,
        selected_section: "Все разделы",
        summary_type: summaryType,
      });

      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "bonchmind_summary.docx";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setNotice({
        tone: "success",
        text: "DOCX подготовлен и отправлен в загрузки браузера.",
      });
    } catch (error) {
      if (handleAuthError(error, router)) return;
      const message =
        error instanceof Error && error.message.includes("404")
          ? "Экспорт еще не подключился на backend. Перезапустите python run_api.py и повторите."
          : "Не удалось экспортировать DOCX. Проверьте backend и повторите попытку.";
      setExportError(message);
      setNotice({
        tone: "warning",
        text: message,
      });
    } finally {
      setIsExporting(false);
    }
  }

  const plannedGroups = isChunkGroupArray(result?.trace?.chunks?.planned_chunk_groups)
    ? result.trace?.chunks?.planned_chunk_groups
    : [];
  const llmCalls = result?.trace?.llm_calls?.length ?? 0;
  const elapsedSeconds = typeof result?.trace?.elapsed_sec === "number" ? Math.round(result.trace.elapsed_sec) : null;
  const fragmentCount = plannedGroups.reduce((total, group) => total + group.chunks.length, 0);

  return (
    <div className="space-y-6">
      <section className="bm-surface rounded-xl p-6 shadow-soft">
        <div className="mb-8 flex items-start justify-between gap-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">Конспект</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">
              Выберите материал и тему — соберём конспект с опорой на источники.
            </p>
          </div>
          <button
            className="bm-button-secondary h-12 px-5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:text-white/55"
            type="button"
            disabled={!result?.text || isExporting}
            onClick={handleExport}
          >
            {isExporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            {isExporting ? "Экспорт..." : "Экспорт"}
          </button>
        </div>

        <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
          <MaterialPicker
            label="Материал"
            materials={materials}
            value={selectedFile}
            onChange={setSelectedFile}
          />

          <SegmentedControl
            label="Тип конспекта"
            options={summaryTypes}
            value={summaryType}
            onChange={setSummaryType}
          />
        </div>

        <label className="mt-6 block space-y-2">
          <span className="text-sm font-semibold text-white">Тема</span>
          <textarea
            className="bm-textarea min-h-32 w-full text-white"
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            placeholder="Например: Что такое Wi-Fi?"
          />
        </label>

        <div className="mt-6 flex flex-wrap items-center gap-4">
          <button
            className="bm-button-primary h-12 px-6 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
            type="button"
            disabled={isLoading || !topic.trim()}
            onClick={handleGenerate}
          >
            {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {isLoading ? "Генерирую..." : "Сгенерировать"}
          </button>
          <button
            className="bm-button-secondary h-12 px-6 text-sm font-bold text-white disabled:cursor-not-allowed disabled:text-white/55"
            type="button"
            disabled={!plannedGroups.length}
            onClick={() => setShowSources((value) => !value)}
          >
            <Search className="h-4 w-4" />
            {showSources ? "Скрыть источники" : "Проверить источники"}
          </button>
          <p className="text-sm text-muted">Первый запуск может быть дольше обычного.</p>
        </div>

        {exportError ? (
          <div className="mt-4 rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
            {exportError}
          </div>
        ) : null}

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

        {result ? (
          <div className="mt-5 flex flex-wrap gap-3">
            <div className="rounded-lg border border-white/10 bg-[#0d1117] px-3 py-2 text-sm text-slate-200">
              Стратегия: <span className="text-white">{result.trace?.strategy || "unknown"}</span>
            </div>
            <div className="rounded-lg border border-white/10 bg-[#0d1117] px-3 py-2 text-sm text-slate-200">
              Фрагменты: <span className="text-white">{fragmentCount}</span>
            </div>
            <div className="rounded-lg border border-white/10 bg-[#0d1117] px-3 py-2 text-sm text-slate-200">
              LLM-вызовы: <span className="text-white">{llmCalls}</span>
            </div>
            <div className="rounded-lg border border-white/10 bg-[#0d1117] px-3 py-2 text-sm text-slate-200">
              Время: <span className="text-white">{elapsedSeconds ? `${elapsedSeconds} c` : "н/д"}</span>
            </div>
          </div>
        ) : null}
      </section>

      {isLoading || result ? (
        <section className="bm-surface rounded-xl p-6 shadow-soft">
          {isLoading ? (
            <div className="bm-surface-deep flex min-h-72 items-center justify-center rounded-xl text-muted">
              <Loader2 className="mr-3 h-5 w-5 animate-spin text-brand" />
              BonchMind собирает источники и пишет конспект...
            </div>
          ) : (
            <pre className="max-h-[560px] overflow-auto whitespace-pre-wrap rounded-xl border border-white/10 bg-[#0d1117] p-5 font-sans text-sm leading-7 text-slate-200">
              {result?.text}
            </pre>
          )}
        </section>
      ) : null}

      {showSources && plannedGroups.length > 0 ? (
        <section className="bm-surface rounded-xl p-6 shadow-soft">
          <div className="mb-5">
            <p className="text-sm font-semibold text-brand">Проверка покрытия</p>
            <h2 className="mt-2 text-2xl font-bold text-white">Чем подтвержден конспект</h2>
            <p className="mt-2 max-w-3xl text-sm leading-7 text-muted">
              Здесь видно, какие разделы и фрагменты поддержали каждый пункт.
            </p>
          </div>

          <div className="space-y-4">
            {plannedGroups.map((group) => {
              const sections = Array.from(
                new Set(group.chunks.map((chunk) => chunk.section).filter(Boolean)),
              );

              return (
                <div key={group.item} className="rounded-lg border border-white/10 bg-[#0d1117] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="text-base font-bold text-white">{group.item}</h3>
                      <p className="mt-1 text-sm text-muted">
                        {group.chunks.length} фрагм. • {sections.slice(0, 3).join("; ") || "нет точных разделов"}
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 grid gap-3">
                    {group.chunks.slice(0, 3).map((chunk) => (
                      <div key={`${group.item}-${chunk.chunk_id}`} className="rounded-md border border-white/10 bg-[#131923] p-3">
                        <div className="text-sm font-semibold text-white">
                          {chunk.section || "Без раздела"}
                        </div>
                        <div className="mt-1 text-xs text-muted">
                          {chunk.source_file} • chunk #{chunk.chunk_id}
                          {typeof chunk.score === "number" ? ` • score ${chunk.score.toFixed(3)}` : ""}
                        </div>
                        <p className="mt-3 text-sm leading-6 text-slate-300">{chunk.text_preview}</p>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
}
