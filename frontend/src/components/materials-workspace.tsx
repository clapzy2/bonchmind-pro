"use client";

import { type ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookCopy,
  BookOpenText,
  Database,
  FileSearch,
  LibraryBig,
  Loader2,
  RefreshCcw,
  Search,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";

import {
  deleteMaterial,
  getMaterialProgress,
  getMaterialSections,
  reindexLibrary,
  reindexMaterial,
  uploadMaterial,
  type MaterialInfo,
  type MaterialProgressResponse,
  type SystemStatus,
} from "@/lib/api";

type MaterialsWorkspaceProps = {
  materials: MaterialInfo[];
  status: SystemStatus;
  onLibraryChange?: () => Promise<void> | void;
};

type Notice = {
  tone: "info" | "warning" | "success";
  text: string;
};

const PREFERENCES_KEY = "bonchmind-materials-preferences";

const idleProgress: MaterialProgressResponse = {
  active: false,
  operation: "idle",
  phase: "",
  message: "",
  progress: 0,
  current_file: "",
  error: "",
};

function getMaterialBadge(label: string) {
  if (label === "ready") {
    return {
      className: "bm-chip bm-chip-ready",
      text: "готов",
    };
  }

  if (label === "plain_text") {
    return {
      className: "bm-chip bm-chip-plain",
      text: "сплошной текст",
    };
  }

  return {
    className: "bm-chip bm-chip-limited",
      text: "ограничен",
  };
}

export function MaterialsWorkspace({ materials, status, onLibraryChange }: MaterialsWorkspaceProps) {
  const [query, setQuery] = useState("");
  const [selectedMaterial, setSelectedMaterial] = useState(materials[0]?.name ?? "");
  const [sectionsCache, setSectionsCache] = useState<Record<string, string[]>>({});
  const [isLoadingSections, setIsLoadingSections] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isReindexingMaterial, setIsReindexingMaterial] = useState(false);
  const [isReindexingLibrary, setIsReindexingLibrary] = useState(false);
  const [progressState, setProgressState] = useState<MaterialProgressResponse>(idleProgress);
  const [hasPendingSync, setHasPendingSync] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const isAnyOperationRunning = isUploading || isDeleting || isReindexingMaterial || isReindexingLibrary;

  const syncLibraryState = useCallback(async () => {
    setSectionsCache({});
    await onLibraryChange?.();
  }, [onLibraryChange]);

  const filteredMaterials = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return materials;
    }

    return materials.filter((material) => material.name.toLowerCase().includes(normalized));
  }, [materials, query]);

  const [prevFilteredMaterials, setPrevFilteredMaterials] = useState(filteredMaterials);

  const selectedMaterialInfo = materials.find((material) => material.name === selectedMaterial) ?? null;
  const sections = selectedMaterial ? (sectionsCache[selectedMaterial] ?? []) : [];

  useEffect(() => {
    if (!materials.length) {
      // Clearing the selection when the library becomes empty is part of the
      // localStorage-restore sync below, not derived render state.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedMaterial("");
      return;
    }

    const raw = window.localStorage.getItem(PREFERENCES_KEY);
    if (!raw) {
      setSelectedMaterial((current) => current || materials[0].name);
      return;
    }

    try {
      const parsed = JSON.parse(raw) as { selectedMaterial?: string };
      if (parsed.selectedMaterial && materials.some((material) => material.name === parsed.selectedMaterial)) {
        setSelectedMaterial(parsed.selectedMaterial);
      } else {
        setSelectedMaterial(materials[0].name);
      }
    } catch {
      window.localStorage.removeItem(PREFERENCES_KEY);
      setSelectedMaterial(materials[0].name);
    }
  }, [materials]);

  useEffect(() => {
    if (!selectedMaterial) {
      return;
    }

    window.localStorage.setItem(
      PREFERENCES_KEY,
      JSON.stringify({
        selectedMaterial,
      }),
    );
  }, [selectedMaterial]);

  useEffect(() => {
    if (!selectedMaterial || sectionsCache[selectedMaterial]) {
      return;
    }

    let isCancelled = false;

    async function loadSections() {
      setIsLoadingSections(true);
      setNotice({
        tone: "info",
        text: "BonchMind читает структуру выбранного материала.",
      });

      const response = await getMaterialSections(selectedMaterial);
      if (isCancelled) {
        return;
      }

      setSectionsCache((current) => ({
        ...current,
        [selectedMaterial]: response.sections,
      }));
      setNotice(null);
      setIsLoadingSections(false);
    }

    loadSections().catch(() => {
      if (isCancelled) {
        return;
      }

      setNotice({
        tone: "warning",
        text: "Не удалось получить список разделов. Проверьте backend и повторите попытку.",
      });
      setIsLoadingSections(false);
    });

    return () => {
      isCancelled = true;
    };
  }, [sectionsCache, selectedMaterial]);

  if (filteredMaterials !== prevFilteredMaterials) {
    setPrevFilteredMaterials(filteredMaterials);
    if (
      filteredMaterials.length &&
      !filteredMaterials.some((material) => material.name === selectedMaterial)
    ) {
      setSelectedMaterial(filteredMaterials[0].name);
    }
  }

  useEffect(() => {
    const shouldPoll = isAnyOperationRunning;
    if (!shouldPoll) {
      return;
    }

    let isCancelled = false;

    async function pullProgress() {
      const response = await getMaterialProgress();
      if (!isCancelled) {
        setProgressState(response);
      }
    }

    pullProgress().catch(() => undefined);
    const timer = window.setInterval(() => {
      pullProgress().catch(() => undefined);
    }, 500);

    return () => {
      isCancelled = true;
      window.clearInterval(timer);
    };
  }, [isAnyOperationRunning]);

  useEffect(() => {
    if (!isAnyOperationRunning || progressState.active) {
      return;
    }

    async function finalize() {
      if (hasPendingSync) {
        await syncLibraryState();
      }

      setNotice({
        tone: progressState.phase === "error" ? "warning" : "success",
        text:
          progressState.message ||
          (progressState.phase === "error"
            ? "Операция с библиотекой завершилась с ошибкой."
            : "Операция с библиотекой завершена."),
      });

      setIsUploading(false);
      setIsDeleting(false);
      setIsReindexingMaterial(false);
      setIsReindexingLibrary(false);
      setHasPendingSync(false);
    }

    finalize().catch(() => {
      setIsUploading(false);
      setIsDeleting(false);
      setIsReindexingMaterial(false);
      setIsReindexingLibrary(false);
      setHasPendingSync(false);
    });
  }, [hasPendingSync, isAnyOperationRunning, progressState, syncLibraryState]);

  async function handleUploadChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || isUploading) {
      return;
    }

    setIsUploading(true);
    setHasPendingSync(true);
    setProgressState({
      active: true,
      operation: "upload",
      phase: "queued",
      message: `Ставлю в очередь загрузку ${file.name}`,
      progress: 0,
      current_file: file.name,
      error: "",
    });
    setNotice({
      tone: "info",
      text: `Загружаю и индексирую ${file.name}. После этого материал сразу появится в библиотеке.`,
    });

    try {
      const response = await uploadMaterial(file);
      if (!response.ok) {
        setNotice({
          tone: "warning",
          text: response.message,
        });
        setIsUploading(false);
        setHasPendingSync(false);
      } else {
        setSelectedMaterial(file.name);
        setNotice({
          tone: "info",
          text: response.message,
        });
        setProgressState(await getMaterialProgress());
      }
    } catch {
      setNotice({
        tone: "warning",
        text: "Не удалось загрузить материал. Проверьте backend и повторите попытку.",
      });
      setProgressState({
        active: false,
        operation: "idle",
        phase: "error",
        message: "Загрузка завершилась с ошибкой",
        progress: 100,
        current_file: file.name,
        error: "upload_failed",
      });
    } finally {
      setIsUploading(false);
      event.target.value = "";
    }
  }

  async function handleDeleteSelected() {
    if (!selectedMaterial || isDeleting) {
      return;
    }

    const isConfirmed = window.confirm(
      `Удалить материал "${selectedMaterial}" из сайта и из индекса BonchMind?`,
    );
    if (!isConfirmed) {
      return;
    }

    setIsDeleting(true);
    setHasPendingSync(true);
    setProgressState({
      active: true,
      operation: "delete",
      phase: "queued",
      message: `Ставлю в очередь удаление ${selectedMaterial}`,
      progress: 0,
      current_file: selectedMaterial,
      error: "",
    });
    setNotice({
      tone: "info",
      text: `Удаляю ${selectedMaterial} из библиотеки и векторной базы.`,
    });

    try {
      const response = await deleteMaterial(selectedMaterial);
      if (!response.ok) {
        setNotice({
          tone: "warning",
          text: response.message,
        });
        setIsDeleting(false);
        setHasPendingSync(false);
      } else {
        setNotice({
          tone: "info",
          text: response.message,
        });
        setProgressState(await getMaterialProgress());
      }
    } catch {
      setNotice({
        tone: "warning",
        text: "Не удалось удалить материал. Попробуйте еще раз после проверки backend.",
      });
      setProgressState({
        active: false,
        operation: "idle",
        phase: "error",
        message: "Удаление завершилось с ошибкой",
        progress: 100,
        current_file: selectedMaterial,
        error: "delete_failed",
      });
    }
  }

  async function handleReindexSelected() {
    if (!selectedMaterial || isReindexingMaterial) {
      return;
    }

    setIsReindexingMaterial(true);
    setHasPendingSync(true);
    setProgressState({
      active: true,
      operation: "reindex_material",
      phase: "queued",
      message: `Ставлю в очередь переиндексацию ${selectedMaterial}`,
      progress: 0,
      current_file: selectedMaterial,
      error: "",
    });
    setNotice({
      tone: "info",
      text: `Переиндексирую ${selectedMaterial}. Это полезно после замены файла или очистки структуры.`,
    });

    try {
      const response = await reindexMaterial(selectedMaterial);
      if (!response.ok) {
        setNotice({
          tone: "warning",
          text: response.message,
        });
        setIsReindexingMaterial(false);
        setHasPendingSync(false);
      } else {
        setSelectedMaterial(selectedMaterial);
        setNotice({
          tone: "info",
          text: response.message,
        });
        setProgressState(await getMaterialProgress());
      }
    } catch {
      setNotice({
        tone: "warning",
        text: "Не удалось переиндексировать материал.",
      });
      setProgressState({
        active: false,
        operation: "idle",
        phase: "error",
        message: "Переиндексация завершилась с ошибкой",
        progress: 100,
        current_file: selectedMaterial,
        error: "reindex_material_failed",
      });
    }
  }

  async function handleReindexLibrary() {
    if (isReindexingLibrary) {
      return;
    }

    setIsReindexingLibrary(true);
    setHasPendingSync(true);
    setProgressState({
      active: true,
      operation: "reindex_library",
      phase: "queued",
      message: "Ставлю в очередь полную пересборку библиотеки",
      progress: 0,
      current_file: "",
      error: "",
    });
    setNotice({
      tone: "info",
      text: "Полностью пересобираю библиотеку из папки docs. Это может занять немного времени.",
    });

    try {
      const response = await reindexLibrary();
      if (!response.ok) {
        setNotice({
          tone: "warning",
          text: response.message,
        });
        setIsReindexingLibrary(false);
        setHasPendingSync(false);
      } else {
        setNotice({
          tone: "info",
          text: response.message,
        });
        setProgressState(await getMaterialProgress());
      }
    } catch {
      setNotice({
        tone: "warning",
        text: "Не удалось переиндексировать библиотеку целиком.",
      });
      setProgressState({
        active: false,
        operation: "idle",
        phase: "error",
        message: "Пересборка библиотеки завершилась с ошибкой",
        progress: 100,
        current_file: "",
        error: "reindex_library_failed",
      });
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-6">
      <section className="bm-surface shrink-0 rounded-xl p-6 shadow-soft">
        <div className="max-w-4xl">
          <p className="text-sm font-semibold text-brand">Библиотека</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-white">Материалы и структура базы</h1>
          <p className="mt-3 text-base leading-7 text-muted">
            Добавляйте файлы, чистите библиотеку и сразу видите, насколько материал готов к работе.
          </p>
        </div>

        <div className="mt-6 flex flex-wrap gap-3">
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".pdf,.txt,.epub,.docx,.md,.fb2,.zip,.html,.htm"
            onChange={handleUploadChange}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isAnyOperationRunning}
            className="bm-button-primary h-11 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            Добавить материал
          </button>
          <button
            type="button"
            onClick={handleReindexLibrary}
            disabled={isAnyOperationRunning}
            className="bm-button-secondary h-11 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isReindexingLibrary ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
            Пересобрать библиотеку
          </button>
        </div>

        {(progressState.active || progressState.phase === "done" || progressState.phase === "error") ? (
          <div className="mt-5 rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="text-sm font-semibold text-white">
                  {progressState.active ? "Индексация в процессе" : progressState.phase === "error" ? "Операция завершилась с ошибкой" : "Последняя операция завершена"}
                </div>
                <div className="mt-1 text-sm text-muted">
                  {progressState.message || "BonchMind готовит библиотеку."}
                </div>
              </div>
              <div className="text-lg font-bold text-white">{progressState.progress}%</div>
            </div>
            <div className="mt-4 h-3 overflow-hidden rounded-full bg-white/8">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  progressState.phase === "error" ? "bg-amber-400" : "bg-[var(--accent)]"
                }`}
                style={{ width: `${Math.max(4, progressState.progress)}%` }}
              />
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.16em] text-white/45">
              <span>Этап: {progressState.phase || "starting"}</span>
              {progressState.current_file ? <span>Файл: {progressState.current_file}</span> : null}
              <span>{progressState.active ? "live" : progressState.phase === "error" ? "error" : "done"}</span>
            </div>
          </div>
        ) : null}

        <div className="mt-8 grid gap-4 lg:grid-cols-4">
          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="flex items-center gap-2 text-white">
              <LibraryBig className="h-4 w-4 text-brand" />
              <span className="text-sm font-semibold">Материалы</span>
            </div>
            <div className="mt-4 text-3xl font-bold text-white">{materials.length}</div>
            <p className="mt-2 text-sm leading-6 text-muted">доступны в библиотеке нового интерфейса</p>
          </div>

          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="flex items-center gap-2 text-white">
              <Database className="h-4 w-4 text-[var(--source)]" />
              <span className="text-sm font-semibold">Фрагменты</span>
            </div>
            <div className="mt-4 text-3xl font-bold text-white">{status.total_chunks}</div>
            <p className="mt-2 text-sm leading-6 text-muted">уже готовы для retrieval и генерации</p>
          </div>

          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="flex items-center gap-2 text-white">
              <BookCopy className="h-4 w-4 text-emerald-400" />
              <span className="text-sm font-semibold">Выбрано</span>
            </div>
            <div className="mt-4 truncate text-lg font-bold text-white">
              {selectedMaterialInfo?.name ?? "Материал не выбран"}
            </div>
            <p className="mt-2 text-sm leading-6 text-muted">
              {selectedMaterialInfo ? `${selectedMaterialInfo.sections_count} разделов по текущим данным` : "Выберите книгу для просмотра структуры"}
            </p>
          </div>

          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="flex items-center gap-2 text-white">
              <Sparkles className="h-4 w-4 text-brand" />
              <span className="text-sm font-semibold">Назначение</span>
            </div>
            <p className="mt-4 text-sm leading-7 text-muted">
              Быстрый контроль: что уже готово для поиска, а что еще стоит проверить.
            </p>
          </div>
        </div>
      </section>

      <div className="grid min-h-0 flex-1 gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <section className="bm-surface flex min-h-0 flex-col rounded-xl p-6 shadow-soft">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-brand">Навигация по базе</p>
              <h2 className="mt-2 text-xl font-bold text-white">Список материалов</h2>
            </div>
            <div className="rounded-lg border border-white/10 bg-[#0d1117] px-3 py-2 text-sm text-slate-200">
              {filteredMaterials.length} из {materials.length}
            </div>
          </div>

          <label className="mt-5 block">
            <span className="sr-only">Поиск по материалам</span>
            <div className="bm-control flex h-12 items-center gap-3 rounded-xl px-4">
              <Search className="h-4 w-4 text-muted" />
              <input
                className="w-full bg-transparent text-sm text-white outline-none placeholder:text-[#677384]"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Найти книгу, учебник или базу"
              />
            </div>
          </label>

          <div className="mt-5 min-h-0 flex-1 overflow-y-auto pr-1 assistant-scroll">
            <div className="space-y-3">
              {filteredMaterials.length > 0 ? (
                filteredMaterials.map((material) => {
                const isActive = material.name === selectedMaterial;
                const badge = getMaterialBadge(material.quality_label);

                return (
                  <button
                    key={material.name}
                    type="button"
                    onClick={() => setSelectedMaterial(material.name)}
                    className={`w-full rounded-lg border p-4 text-left transition ${
                      isActive
                        ? "border-brand bg-[rgba(240,90,26,0.09)] shadow-[0_12px_28px_rgba(0,0,0,0.14)]"
                        : "border-white/10 bg-[#0f1319] hover:border-white/20 hover:bg-[#121823]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-white">{material.name}</div>
                        <div className="mt-2 flex items-center gap-2 text-xs">
                          <span className="uppercase tracking-[0.18em] text-white/40">
                            {material.sections_count} разделов
                          </span>
                          <span
                            className={badge.className}
                          >
                            {badge.text}
                          </span>
                        </div>
                        <div className="mt-2 text-xs leading-5 text-muted">{material.quality_reason}</div>
                      </div>
                      <FileSearch className={`h-4 w-4 shrink-0 ${isActive ? "text-brand" : "text-white/35"}`} />
                    </div>
                  </button>
                );
              })
              ) : (
                <div className="rounded-lg border border-dashed border-white/10 bg-[#0f1319] p-5 text-sm leading-7 text-muted">
                  По этому запросу материалы не найдены. Попробуйте часть имени файла или очистите поиск.
                </div>
              )}
            </div>
          </div>
        </section>

        <section className="bm-surface flex min-h-0 flex-col rounded-xl p-6 shadow-soft">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-brand">Структура материала</p>
              <h2 className="mt-2 text-xl font-bold text-white">
                {selectedMaterialInfo?.name ?? "Выберите материал"}
              </h2>
              <p className="mt-3 text-sm leading-7 text-muted">
                Разделы, доступные для поиска, конспектов и ссылок на источник.
              </p>
            </div>
            <BookOpenText className="mt-1 h-5 w-5 text-brand" />
          </div>

          {notice ? (
            <div
              className={`mt-5 rounded-md px-4 py-3 text-sm ${
                notice.tone === "warning"
                  ? "border border-amber-500/30 bg-amber-500/10 text-amber-100"
                  : notice.tone === "success"
                    ? "border border-emerald-500/30 bg-emerald-500/10 text-emerald-100"
                  : "border border-cyan-500/30 bg-cyan-500/10 text-cyan-100"
              }`}
            >
              {notice.text}
            </div>
          ) : null}

          <div className="mt-5 rounded-xl border border-white/10 bg-[#0d1117] p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-3 text-sm">
              <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-slate-200">
                Файл: <span className="text-white">{selectedMaterialInfo?.name ?? "не выбран"}</span>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-slate-200">
                Разделы: <span className="text-white">{selectedMaterialInfo?.sections_count ?? 0}</span>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-slate-200">
                Загружено: <span className="text-white">{sections.length}</span>
              </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleReindexSelected}
                  disabled={!selectedMaterialInfo || isAnyOperationRunning}
                  className="bm-button-secondary h-10 px-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isReindexingMaterial ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
                  Переиндексировать
                </button>
                <button
                  type="button"
                  onClick={handleDeleteSelected}
                  disabled={!selectedMaterialInfo || isAnyOperationRunning}
                  className="bm-button-danger h-10 px-3 text-sm font-medium text-red-100 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                  Удалить
                </button>
              </div>
            </div>
          </div>

          <div className="mt-5 min-h-0 flex-1 overflow-y-auto pr-1 assistant-scroll">
            {isLoadingSections ? (
              <div className="flex min-h-56 items-center justify-center rounded-lg border border-white/10 bg-[#0d1117] text-muted">
                <Loader2 className="mr-3 h-5 w-5 animate-spin text-brand" />
                Читаю разделы выбранного материала...
              </div>
            ) : !selectedMaterialInfo ? (
              <div className="rounded-lg border border-dashed border-white/10 bg-[#0d1117] p-5 text-sm leading-7 text-muted">
                Слева появится список книг. Выберите одну из них, и здесь откроется ее структура.
              </div>
            ) : sections.length > 0 ? (
              <div className="grid gap-3 md:grid-cols-2">
                {sections.map((section, index) => (
                  <div key={`${section}-${index}`} className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
                    <div className="text-xs uppercase tracking-[0.18em] text-white/35">Раздел {index + 1}</div>
                    <div className="mt-3 text-sm font-semibold leading-6 text-white">{section}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-white/10 bg-[#0d1117] p-5 text-sm leading-7 text-muted">
                У этого материала нет явных разделов. Его все равно можно использовать в ассистенте и поиске как сплошной текст.
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
