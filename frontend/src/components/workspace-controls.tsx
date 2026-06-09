"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, FileStack, Search } from "lucide-react";

import type { MaterialInfo } from "@/lib/api";

type SegmentedControlProps = {
  label: string;
  options: string[];
  value: string;
  onChange: (value: string) => void;
};

type MaterialPickerProps = {
  label: string;
  materials: MaterialInfo[];
  value: string;
  onChange: (value: string) => void;
  includeAllOption?: boolean;
};

const qualityMeta: Record<string, { label: string; tone: string; hint: string }> = {
  ready: {
    label: "Готов",
    tone: "bm-chip-ready",
    hint: "Хорошо подходит для конспектов, поиска и ссылок.",
  },
  plain_text: {
    label: "Текст",
    tone: "bm-chip-plain",
    hint: "Работает как линейный источник без выраженной структуры разделов.",
  },
  limited: {
    label: "Ограничен",
    tone: "bm-chip-limited",
    hint: "Можно использовать, но качество структуры и попаданий может быть ниже.",
  },
  hidden: {
    label: "Скрыт",
    tone: "bm-chip-neutral",
    hint: "Материал почти не пригоден для поиска и показа пользователю.",
  },
};

function getQualityMeta(label: string) {
  return qualityMeta[label] ?? qualityMeta.limited;
}

function shortenName(value: string) {
  if (value.length <= 52) {
    return value;
  }

  return `${value.slice(0, 49)}...`;
}

export function SegmentedControl({ label, options, value, onChange }: SegmentedControlProps) {
  return (
    <div className="space-y-2">
      <div className="text-sm font-semibold text-white">{label}</div>
      <div className="bm-segmented">
        {options.map((option) => {
          const active = option === value;

          return (
            <button
              key={option}
              type="button"
              className={`bm-segmented-item ${active ? "bm-segmented-item-active" : ""}`}
              onClick={() => onChange(option)}
            >
              {option}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function MaterialPicker({
  label,
  materials,
  value,
  onChange,
  includeAllOption = true,
}: MaterialPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  const selectedMaterial = materials.find((material) => material.name === value);
  const selectedMeta = selectedMaterial ? getQualityMeta(selectedMaterial.quality_label) : null;

  const filteredMaterials = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return materials;
    }

    return materials.filter((material) => {
      return (
        material.name.toLowerCase().includes(normalized) ||
        material.quality_reason.toLowerCase().includes(normalized)
      );
    });
  }, [materials, query]);

  return (
    <div ref={rootRef} className="space-y-2">
      <div className="text-sm font-semibold text-white">{label}</div>
      <div className="bm-picker">
        <button
          type="button"
          className={`bm-picker-trigger ${open ? "bm-picker-trigger-open" : ""}`}
          onClick={() => setOpen((current) => !current)}
          aria-expanded={open}
        >
          <div className="min-w-0 flex-1 text-left">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted">
              {selectedMaterial ? "Выбран материал" : "Охват поиска"}
            </div>
            <div className="mt-1 truncate text-base font-semibold text-white">
              {selectedMaterial ? selectedMaterial.name : "Все материалы"}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
              {selectedMaterial ? (
                <>
                  <span>{selectedMaterial.sections_count} разделов</span>
                  <span className={`bm-chip ${selectedMeta?.tone}`}>{selectedMeta?.label}</span>
                </>
              ) : (
                <span>Поиск сразу по всей библиотеке</span>
              )}
            </div>
          </div>
          <ChevronDown className={`h-5 w-5 shrink-0 text-muted transition ${open ? "rotate-180 text-white" : ""}`} />
        </button>

        {open ? (
          <div className="bm-picker-panel">
            <div className="bm-picker-search">
              <Search className="h-4 w-4 text-muted" />
              <input
                className="w-full bg-transparent text-sm text-white outline-none placeholder:text-[#677384]"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Найти книгу, конспект или базу"
              />
            </div>

            <div className="bm-picker-options">
              {includeAllOption ? (
                <button
                  type="button"
                  className={`bm-picker-option ${value === "Все материалы" ? "bm-picker-option-active" : ""}`}
                  onClick={() => {
                    onChange("Все материалы");
                    setOpen(false);
                    setQuery("");
                  }}
                >
                  <div className="flex min-w-0 flex-1 items-start gap-3">
                    <div className="mt-0.5 rounded-lg border border-white/10 bg-white/5 p-2">
                      <FileStack className="h-4 w-4 text-brand" />
                    </div>
                    <div className="min-w-0 text-left">
                      <div className="text-sm font-semibold text-white">Все материалы</div>
                      <div className="mt-1 text-sm leading-6 text-muted">
                        Широкий охват по всей библиотеке. Полезно для тем, которые могут лежать в нескольких источниках.
                      </div>
                    </div>
                  </div>
                  {value === "Все материалы" ? <Check className="h-4 w-4 text-brand" /> : null}
                </button>
              ) : null}

              {filteredMaterials.map((material) => {
                const meta = getQualityMeta(material.quality_label);
                const active = material.name === value;

                return (
                  <button
                    key={material.name}
                    type="button"
                    className={`bm-picker-option ${active ? "bm-picker-option-active" : ""}`}
                    onClick={() => {
                      onChange(material.name);
                      setOpen(false);
                      setQuery("");
                    }}
                  >
                    <div className="min-w-0 flex-1 text-left">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="truncate text-sm font-semibold text-white">
                          {shortenName(material.name)}
                        </div>
                        <span className={`bm-chip ${meta.tone}`}>{meta.label}</span>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-muted">
                        <span>{material.sections_count} разделов</span>
                        <span>{material.quality_reason || meta.hint}</span>
                      </div>
                    </div>
                    {active ? <Check className="h-4 w-4 shrink-0 text-brand" /> : null}
                  </button>
                );
              })}

              {!filteredMaterials.length ? (
                <div className="rounded-xl border border-dashed border-white/10 bg-[#0f1319] px-4 py-5 text-sm text-muted">
                  Ничего не найдено. Попробуйте часть имени файла или другой запрос.
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
