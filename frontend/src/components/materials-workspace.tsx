"use client";

import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  BookCopy,
  LibraryBig,
  Loader2,
  RefreshCcw,
  Search,
  Trash2,
  Upload,
} from "lucide-react";

import type { MaterialInfo } from "@/lib/api";
import { useMaterialOperations } from "@/lib/use-material-operations";

type MaterialsWorkspaceProps = {
  materials: MaterialInfo[];
  onLibraryChange?: () => Promise<void> | void;
};

const PREFERENCES_KEY = "bonchmind-materials-preferences";

function getMaterialBadge(label: string) {
  if (label === "ready" || label === "plain_text") {
    return {
      className: "bm-chip bm-chip-ready",
      text: "Готов",
    };
  }

  return {
    className: "bm-chip bm-chip-limited",
    text: "Требует проверки",
  };
}

export function MaterialsWorkspace({ materials, onLibraryChange }: MaterialsWorkspaceProps) {
  const [query, setQuery] = useState("");
  const [selectedMaterial, setSelectedMaterial] = useState(materials[0]?.name ?? "");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const operations = useMaterialOperations({
    onSync: async () => {
      await onLibraryChange?.();
    },
  });
  const { progress, notice, isRunning, activeOperation } = operations;

  const filteredMaterials = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return materials;
    }

    return materials.filter((material) => material.name.toLowerCase().includes(normalized));
  }, [materials, query]);

  const [prevFilteredMaterials, setPrevFilteredMaterials] = useState(filteredMaterials);

  const selectedMaterialInfo = materials.find((material) => material.name === selectedMaterial) ?? null;

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

  if (filteredMaterials !== prevFilteredMaterials) {
    setPrevFilteredMaterials(filteredMaterials);
    if (
      filteredMaterials.length &&
      !filteredMaterials.some((material) => material.name === selectedMaterial)
    ) {
      setSelectedMaterial(filteredMaterials[0].name);
    }
  }

  function handleUploadChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset the input first so re-selecting the same file still fires change.
    event.target.value = "";
    if (!file || isRunning) {
      return;
    }
    void operations.uploadFile(file, (materialName) => setSelectedMaterial(materialName));
  }

  function handleReindexSelected(materialName: string) {
    if (!materialName || isRunning) {
      return;
    }
    void operations.reindexFile(materialName);
  }

  function handleDeleteSelected(materialName: string) {
    if (!materialName || isRunning) {
      return;
    }

    const isConfirmed = window.confirm(
      `Удалить материал "${materialName}" из сайта и из индекса BonchMind?`,
    );
    if (!isConfirmed) {
      return;
    }

    void operations.deleteFile(materialName);
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-6">
      <section className="bm-surface shrink-0 rounded-xl p-6 shadow-soft">
        <div className="max-w-4xl">
          <h1 className="text-2xl font-bold tracking-tight text-white">Библиотека</h1>
          <p className="mt-2 text-sm leading-6 text-muted">
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
            disabled={isRunning}
            className="bm-button-primary h-11 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-70"
          >
            {activeOperation === "upload" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            Добавить материал
          </button>
          <button
            type="button"
            onClick={() => operations.reindexAll()}
            disabled={isRunning}
            className="bm-button-secondary h-11 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-70"
          >
            {activeOperation === "reindex_library" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
            Пересобрать библиотеку
          </button>
        </div>

        {(progress.active || progress.phase === "done" || progress.phase === "error") ? (
          <div className="mt-5 rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="text-sm font-semibold text-white">
                  {progress.active ? "Индексация в процессе" : progress.phase === "error" ? "Операция завершилась с ошибкой" : "Последняя операция завершена"}
                </div>
                <div className="mt-1 text-sm text-muted">
                  {progress.message || "BonchMind готовит библиотеку."}
                </div>
              </div>
              <div className="text-lg font-bold text-white">{progress.progress}%</div>
            </div>
            <div className="mt-4 h-3 overflow-hidden rounded-full bg-white/8">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  progress.phase === "error" ? "bg-amber-400" : "bg-[var(--accent)]"
                }`}
                style={{ width: `${Math.max(4, progress.progress)}%` }}
              />
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.16em] text-white/45">
              <span>Этап: {progress.phase || "starting"}</span>
              {progress.current_file ? <span>Файл: {progress.current_file}</span> : null}
              <span>{progress.active ? "live" : progress.phase === "error" ? "error" : "done"}</span>
            </div>
          </div>
        ) : null}

        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-white/10 bg-[#0f1319] p-4">
            <div className="flex items-center gap-2 text-white">
              <LibraryBig className="h-4 w-4 text-brand" />
              <span className="text-sm font-semibold">Материалы</span>
            </div>
            <div className="mt-4 text-3xl font-bold text-white">{materials.length}</div>
            <p className="mt-2 text-sm leading-6 text-muted">в вашей библиотеке</p>
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
              {selectedMaterialInfo ? "Действия доступны прямо в карточке." : "Выберите материал из списка ниже."}
            </p>
          </div>
        </div>
      </section>

      <section className="bm-surface flex min-h-0 flex-1 flex-col rounded-xl p-6 shadow-soft">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-white">Список материалов</h2>
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
              placeholder="Найти материал по имени"
            />
          </div>
        </label>

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

        <div className="mt-5 min-h-0 flex-1 overflow-y-auto pr-1 assistant-scroll">
          <div className="space-y-3">
            {filteredMaterials.length > 0 ? (
              filteredMaterials.map((material) => {
                const isActive = material.name === selectedMaterial;
                const badge = getMaterialBadge(material.quality_label);
                const isCardReindexing =
                  activeOperation === "reindex_material" && progress.current_file === material.name;
                const isCardDeleting =
                  activeOperation === "delete" && progress.current_file === material.name;

                return (
                  <div
                    key={material.name}
                    onClick={() => setSelectedMaterial(material.name)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedMaterial(material.name);
                      }
                    }}
                    role="button"
                    tabIndex={0}
                    className={`flex w-full flex-wrap items-center justify-between gap-3 rounded-lg border p-4 text-left transition ${
                      isActive
                        ? "border-brand bg-[rgba(240,90,26,0.09)] shadow-[0_12px_28px_rgba(0,0,0,0.14)]"
                        : "border-white/10 bg-[#0f1319] hover:border-white/20 hover:bg-[#121823]"
                    }`}
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <div className="min-w-0 truncate text-sm font-semibold text-white">{material.name}</div>
                      <span className={badge.className}>{badge.text}</span>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelectedMaterial(material.name);
                          handleReindexSelected(material.name);
                        }}
                        disabled={isRunning}
                        className="bm-button-secondary h-9 px-3 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {isCardReindexing ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <RefreshCcw className="h-3.5 w-3.5" />
                        )}
                        Переиндексировать
                      </button>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelectedMaterial(material.name);
                          handleDeleteSelected(material.name);
                        }}
                        disabled={isRunning}
                        className="bm-button-danger h-9 px-3 text-xs font-medium text-red-100 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {isCardDeleting ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" />
                        )}
                        Удалить
                      </button>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="rounded-lg border border-dashed border-white/10 bg-[#0f1319] p-5 text-sm leading-7 text-muted">
                По этому запросу материалы не найдены. Очистите поиск или загрузите новый файл.
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
