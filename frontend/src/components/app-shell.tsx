"use client";

import { useCallback, useEffect, useState } from "react";

import { getMaterials, getSystemStatus, type ApiHealth, type MaterialInfo, type SummaryResponse, type SystemStatus } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Sidebar } from "@/components/sidebar";
import { SourcePanel } from "@/components/source-panel";
import { AdminWorkspace } from "@/components/admin-workspace";
import { AssistantWorkspace } from "@/components/assistant-workspace";
import { MaterialsWorkspace } from "@/components/materials-workspace";
import { SummaryWorkspace } from "@/components/summary-workspace";
import { Topbar } from "@/components/topbar";
import type { WorkspaceSection } from "@/lib/workspace-section";

type AppShellProps = {
  health: ApiHealth;
  materials: MaterialInfo[];
  status: SystemStatus;
};

const ACTIVE_SECTION_KEY = "bonchmind-active-section";
// Stale localStorage values for sections removed in Stage 7d ("quality",
// "settings") fail this check and fall back to the default "assistant".
// "admin" is valid for everyone here, but a non-superuser is bounced off it
// at render time (see resolvedSection below).
const VALID_SECTIONS: readonly WorkspaceSection[] = [
  "summary",
  "assistant",
  "materials",
  "admin",
];

function isWorkspaceSection(value: unknown): value is WorkspaceSection {
  return typeof value === "string" && (VALID_SECTIONS as readonly string[]).includes(value);
}

function normalizeMaterial(material: MaterialInfo): MaterialInfo {
  const sectionsCount = Number(material.sections_count ?? 0);
  const inferredQuality = sectionsCount > 0 ? "ready" : "plain_text";

  return {
    ...material,
    sections_count: sectionsCount,
    quality_label: material.quality_label || inferredQuality,
    quality_reason:
      material.quality_reason ||
      (sectionsCount > 0
        ? "Материал хорошо подходит для поиска, конспектов и ссылок на источники."
        : "Сплошной текст без явных разделов: хорош для чтения и диалога, слабее для навигации."),
  };
}

function getVisibleMaterials(materials: MaterialInfo[]): MaterialInfo[] {
  return materials.map(normalizeMaterial).filter((material) => material.quality_label !== "hidden");
}

export function AppShell({ health, materials, status }: AppShellProps) {
  const { user } = useAuth();
  const isSuperuser = Boolean(user?.is_superuser);
  const [lastRun, setLastRun] = useState<SummaryResponse | null>(null);
  const [activeSection, setActiveSection] = useState<WorkspaceSection>(() => {
    // SSR-safe initial read of the persisted tab; client-only because the
    // shell is "use client".
    if (typeof window === "undefined") return "assistant";
    const stored = window.localStorage.getItem(ACTIVE_SECTION_KEY);
    return isWorkspaceSection(stored) ? stored : "assistant";
  });
  const [materialsState, setMaterialsState] = useState<MaterialInfo[]>(() => getVisibleMaterials(materials));
  const [statusState, setStatusState] = useState<SystemStatus>(status);
  const [prevMaterials, setPrevMaterials] = useState(materials);
  const [prevStatus, setPrevStatus] = useState(status);

  if (materials !== prevMaterials) {
    setPrevMaterials(materials);
    setMaterialsState(getVisibleMaterials(materials));
  }

  if (status !== prevStatus) {
    setPrevStatus(status);
    setStatusState(status);
  }

  // Persist the active tab so F5 (or any client-side re-mount) keeps the
  // user on the screen they were last using instead of bouncing back to
  // "Конспект".
  useEffect(() => {
    window.localStorage.setItem(ACTIVE_SECTION_KEY, activeSection);
  }, [activeSection]);

  const refreshLibraryState = useCallback(async () => {
    const [materialsResponse, nextStatus] = await Promise.all([getMaterials(), getSystemStatus()]);
    setMaterialsState(getVisibleMaterials(materialsResponse.materials));
    setStatusState(nextStatus);
  }, []);

  // A non-superuser must never see the admin screen even if "admin" was
  // persisted while they had elevated rights (or via a hand-edited
  // localStorage). The backend gates /api/admin/* independently; this is just
  // the UI guard.
  const resolvedSection: WorkspaceSection =
    activeSection === "admin" && !isSuperuser ? "assistant" : activeSection;

  return (
    <div className="app-shell">
      <Sidebar
        activeSection={resolvedSection}
        materials={materialsState}
        isSuperuser={isSuperuser}
        onSectionChange={setActiveSection}
      />
      <div className="main-area">
        <Topbar activeSection={resolvedSection} health={health} />
        <div className="workspace">
          {resolvedSection === "summary" ? (
            <SummaryWorkspace
              materials={materialsState}
              onResult={setLastRun}
              onLibraryChange={refreshLibraryState}
            />
          ) : resolvedSection === "assistant" ? (
            <AssistantWorkspace materials={materialsState} onLibraryChange={refreshLibraryState} />
          ) : resolvedSection === "admin" ? (
            <AdminWorkspace />
          ) : (
            <MaterialsWorkspace materials={materialsState} onLibraryChange={refreshLibraryState} />
          )}
        </div>
      </div>
      <SourcePanel activeSection={resolvedSection} status={statusState} lastRun={lastRun} />
    </div>
  );
}
