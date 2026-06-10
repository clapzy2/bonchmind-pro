"use client";

import { useState } from "react";

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
  const [activeSection, setActiveSection] = useState<WorkspaceSection>("summary");
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

  async function refreshLibraryState() {
    const [materialsResponse, nextStatus] = await Promise.all([getMaterials(), getSystemStatus()]);
    setMaterialsState(getVisibleMaterials(materialsResponse.materials));
    setStatusState(nextStatus);
  }

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
