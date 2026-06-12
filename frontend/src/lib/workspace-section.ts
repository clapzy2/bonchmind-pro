/**
 * The real screens of the app. "quality" and "settings" were removed in
 * Stage 7d: quality moved into compact diagnostics blocks inside Summary /
 * Assistant, and Settings had no content yet. Stale localStorage values for
 * the removed sections fail the app-shell's isWorkspaceSection check and
 * fall back to the default "assistant".
 */
export type WorkspaceSection = "summary" | "assistant" | "materials";
