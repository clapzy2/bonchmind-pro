"use client";

import { useEffect, useState } from "react";

import { getBillingMe, type BillingCounter, type BillingMe } from "@/lib/api";
import { USAGE_CHANGED_EVENT } from "@/lib/paywall";

/**
 * Compact plan + usage readout (Stage 12), shown in the side panel on every
 * screen. Self-fetches ``/api/billing/me`` on mount, when ``refreshKey``
 * changes (tab switch), and whenever a billable action fires the
 * ``bonchmind:usage-changed`` event — so the numbers tick up live.
 */

const PLAN_LABEL: Record<string, string> = { free: "Free", pro: "Pro", org: "Org" };

function UsageRow({ label, counter }: { label: string; counter: BillingCounter }) {
  const pct = counter.limit > 0 ? Math.min(100, Math.round((counter.used / counter.limit) * 100)) : 0;
  const atLimit = counter.limit > 0 && counter.used >= counter.limit;
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-muted">
        <span>{label}</span>
        <span className={`tabular-nums ${atLimit ? "text-amber-300" : "text-slate-300"}`}>
          {counter.used}/{counter.limit}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/8">
        <div
          className={`h-full rounded-full transition-all ${atLimit ? "bg-amber-400" : "bg-[var(--accent)]"}`}
          style={{ width: `${Math.max(4, pct)}%` }}
        />
      </div>
    </div>
  );
}

export function UsagePanel({ refreshKey }: { refreshKey?: string | number }) {
  const [billing, setBilling] = useState<BillingMe | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      getBillingMe()
        .then((next) => {
          if (!cancelled) {
            setBilling(next);
          }
        })
        .catch(() => undefined);
    };
    load();
    window.addEventListener(USAGE_CHANGED_EVENT, load);
    return () => {
      cancelled = true;
      window.removeEventListener(USAGE_CHANGED_EVENT, load);
    };
  }, [refreshKey]);

  if (!billing) {
    return null;
  }

  return (
    <div className="mt-6 rounded-xl border border-[var(--line)] bg-[rgba(255,255,255,0.03)] p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-white">Тариф и лимиты</div>
        <span className="rounded-md border border-white/10 bg-[#0d1117] px-2 py-0.5 text-xs font-semibold text-slate-200">
          {PLAN_LABEL[billing.plan] ?? billing.plan}
        </span>
      </div>

      <div className="mt-3 space-y-3">
        <UsageRow label="Вопросы (сегодня)" counter={billing.usage.chat} />
        <UsageRow label="Конспекты (сегодня)" counter={billing.usage.summary} />
        <UsageRow label="Материалы" counter={billing.usage.materials} />
      </div>

      {billing.plan === "free" ? (
        <p className="mt-3 text-xs leading-5 muted">
          Лимиты бесплатного тарифа. Pro снимает дневные ограничения и расширяет библиотеку.
        </p>
      ) : null}
    </div>
  );
}
