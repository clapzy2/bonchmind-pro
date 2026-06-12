import { BookOpen, FileText, MessageSquareText, Upload } from "lucide-react";
import type { MaterialInfo } from "@/lib/api";
import type { WorkspaceSection } from "@/components/workspace-sections";

type SidebarProps = {
  activeSection: WorkspaceSection;
  materials: MaterialInfo[];
  onSectionChange: (section: WorkspaceSection) => void;
};

const navItems = [
  { key: "assistant", label: "Ассистент", icon: MessageSquareText },
  { key: "summary", label: "Конспект", icon: FileText },
  { key: "materials", label: "Библиотека", icon: BookOpen },
];

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

export function Sidebar({ activeSection, materials, onSectionChange }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--accent)] font-bold text-white">
            B
          </div>
          <div>
            <div className="text-base font-bold">BonchMind Pro</div>
            <div className="text-xs muted">Учебная рабочая станция</div>
          </div>
        </div>
      </div>

      <nav className="space-y-1">
        {navItems.map((item) => (
          <button
            className={`nav-item ${activeSection === item.key ? "nav-item-active" : ""}`}
            key={item.label}
            type="button"
            onClick={() => onSectionChange(item.key as WorkspaceSection)}
          >
            <item.icon size={18} />
            <div className="min-w-0 flex-1">
              <span className="truncate">{item.label}</span>
            </div>
          </button>
        ))}
      </nav>

      <div className="mt-8 rounded-lg border border-[var(--line)] bg-[rgba(255,255,255,0.03)] p-3">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-sm font-semibold">Материалы</div>
          <Upload className="accent" size={16} />
        </div>
        <div className="space-y-2">
          {materials.length === 0 ? (
            <div className="rounded-md border border-dashed border-[var(--line)] p-3 text-sm muted">
              Backend доступен, но материалы пока не найдены.
            </div>
          ) : (
            materials.slice(0, 4).map((material) => {
              const badge = getMaterialBadge(material.quality_label);
              return (
                <div className="rounded-lg border border-white/6 bg-[rgba(255,255,255,0.025)] p-3" key={material.name}>
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0 truncate text-sm font-medium">{material.name}</div>
                    <span className={badge.className}>{badge.text}</span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </aside>
  );
}
