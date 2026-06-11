"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import {
  getHealth,
  getMaterials,
  getSystemStatus,
  UnauthorizedError,
  type ApiHealth,
  type MaterialInfo,
  type SystemStatus,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const offlineHealth: ApiHealth = { status: "offline" };

const offlineStatus: SystemStatus = {
  llm_mode: "offline",
  model: "backend unavailable",
  embedding_model: "unknown",
  reranker_model: "unknown",
  chunk_size: 0,
  hyde_enabled: false,
  total_books: 0,
  total_chunks: 0,
};

type WorkspaceData = {
  health: ApiHealth;
  status: SystemStatus;
  materials: MaterialInfo[];
};

export default function Home() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [dataLoading, setDataLoading] = useState(true);

  // Auth gate. Wait for the bootstrap probe to finish before deciding;
  // sending an unauthenticated user to /login on the first tick would flash
  // the login form for users with a valid cookie.
  useEffect(() => {
    if (!loading && user === null) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  // Client-side data fetch — replaces the previous server-side Promise.all
  // which was always anonymous and produced fallback shapes. We now know we
  // have a session by the time this runs.
  useEffect(() => {
    if (loading || user === null) {
      return;
    }
    let cancelled = false;
    (async () => {
      setDataLoading(true);
      try {
        const [health, status, materialsResponse] = await Promise.all([
          getHealth(),
          getSystemStatus(),
          getMaterials(),
        ]);
        if (cancelled) return;
        setData({
          health,
          status,
          materials: materialsResponse.materials,
        });
      } catch (error) {
        if (cancelled) return;
        if (error instanceof UnauthorizedError) {
          router.replace("/login");
          return;
        }
        setData({
          health: offlineHealth,
          status: offlineStatus,
          materials: [],
        });
      } finally {
        if (!cancelled) {
          setDataLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loading, user, router]);

  if (loading || (user !== null && dataLoading) || (!loading && user === null) || data === null) {
    return (
      <main className="auth-splash">
        <div className="auth-splash-card">
          <div className="auth-splash-spinner" aria-hidden />
          <div className="muted">Загрузка рабочей области…</div>
        </div>
      </main>
    );
  }

  return <AppShell health={data.health} materials={data.materials} status={data.status} />;
}
