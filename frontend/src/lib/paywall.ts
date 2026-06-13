import { QuotaError } from "@/lib/api";

/**
 * Human-readable "you hit a plan limit" copy for a caught error (Stage 12).
 * Returns ``null`` if the error isn't a quota rejection, so callers can do
 * ``const text = paywallText(err); if (text) { ...show paywall... }`` and fall
 * through to their normal error handling otherwise.
 */
const ACTION_LABEL: Record<string, string> = {
  chat: "вопросы ассистенту",
  summary: "конспекты",
  upload: "материалы",
};

export function paywallText(error: unknown): string | null {
  if (!(error instanceof QuotaError)) {
    return null;
  }
  if (error.action === "upload") {
    return `Достигнут лимит материалов (${error.used}/${error.limit}) на тарифе «${error.plan}». Удалите лишнее или обновите тариф.`;
  }
  const what = ACTION_LABEL[error.action] ?? error.action;
  return `Дневной лимит исчерпан: ${what} ${error.used}/${error.limit} (тариф «${error.plan}»). Лимит обновится завтра или после апгрейда.`;
}

/**
 * Lightweight pub/sub so the usage panel can refresh right after a billable
 * action without threading callbacks through every screen. Fire-and-forget.
 */
export const USAGE_CHANGED_EVENT = "bonchmind:usage-changed";

export function notifyUsageChanged(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(USAGE_CHANGED_EVENT));
  }
}
