"use client";

import { useCallback, useEffect, useState } from "react";

import { getMaterials, getSystemStatus, type ApiHealth, type MaterialInfo, type SummaryResponse, type SystemStatus } from "@/lib/api";
import { Sidebar } from "@/components/sidebar";
import { SourcePanel } from "@/components/source-panel";
import { AssistantWorkspace } from "@/components/assistant-workspace";
import { MaterialsWorkspace } from "@/components/materials-workspace";
import { QualityWorkspace } from "@/components/quality-workspace";
import { SummaryWorkspace } from "@/components/summary-workspace";
import { Topbar } from "@/components/topbar";
import { WorkspaceSectionView, type WorkspaceSection } from "@/components/workspace-sections";

type AppShellProps = {
  health: ApiHealth;
  materials: MaterialInfo[];
  status: SystemStatus;
};

const ACTIVE_SECTION_KEY = "bonchmind-active-section";
const VALID_SECTIONS: readonly WorkspaceSection[] = [
  "summary",
  "assistant",
  "materials",
  "quality",
  "settings",
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

  return (
    <div className="app-shell">
      <Sidebar
        activeSection={activeSection}
        materials={materialsState}
        onSectionChange={setActiveSection}
      />
      <div className="main-area">
        <Topbar activeSection={activeSection} health={health} />
        <div className="workspace">
          {activeSection === "summary" ? (
            <SummaryWorkspace materials={materialsState} onResult={setLastRun} />
          ) : activeSection === "assistant" ? (
            <AssistantWorkspace materials={materialsState} />
          ) : activeSection === "materials" ? (
            <MaterialsWorkspace materials={materialsState} status={statusState} onLibraryChange={refreshLibraryState} />
          ) : activeSection === "quality" ? (
            <QualityWorkspace lastRun={lastRun} />
          ) : (
            <WorkspaceSectionView
              activeSection={activeSection}
              lastRun={lastRun}
              materials={materialsState}
              status={statusState}
            />
          )}
        </div>
      </div>
      <SourcePanel activeSection={activeSection} status={statusState} lastRun={lastRun} />
    </div>
  );
}
