"use client";

import { Loader2, X } from "lucide-react";

import type { MaterialProgressResponse } from "@/lib/api";
import type { MaterialOperationNotice } from "@/lib/use-material-operations";

type UploadInlineProps = {
  progress: MaterialProgressResponse;
  notice: MaterialOperationNotice | null;
  /** Cancel the in-flight upload. When provided, an "Отменить" control shows. */
  onCancel?: () => void;
  /** True once cancel was clicked — the control shows "Отменяю…" and disables. */
  cancelling?: boolean;
};

/**
 * Compact upload feedback for the inline paperclip in Assistant / Summary
 * (Stage 7c). Shows a thin progress bar while an upload is in flight and the
 * resulting success/error notice afterwards. Kept separate from each
 * screen's own chat/summary notice so the two never clobber each other.
 */
export function UploadInline({ progress, notice, onCancel, cancelling }: UploadInlineProps) {
  const showProgress = progress.active && progress.operation === "upload";

  if (!showProgress && !notice) {
    return null;
  }

  return (
    <div className="mt-4 space-y-3">
      {showProgress ? (
        <div className="rounded-md border border-white/10 bg-[#0f1319] px-4 py-3">
          <div className="flex items-center gap-3 text-sm text-slate-200">
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-brand" />
            <span className="min-w-0 flex-1 truncate">
              Загружаю «{progress.current_file}»… {progress.progress}%
            </span>
            {onCancel ? (
              <button
                type="button"
                onClick={onCancel}
                disabled={cancelling}
                className="flex shrink-0 items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-xs text-slate-300 transition hover:border-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                <X className="h-3.5 w-3.5" />
                {cancelling ? "Отменяю…" : "Отменить"}
              </button>
            ) : null}
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/8">
            <div
              className="h-full rounded-full bg-[var(--accent)] transition-all duration-300"
              style={{ width: `${Math.max(4, progress.progress)}%` }}
            />
          </div>
        </div>
      ) : null}

      {notice ? (
        <div
          className={`rounded-md px-4 py-3 text-sm ${
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
    </div>
  );
}
