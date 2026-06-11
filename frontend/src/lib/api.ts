export type ApiHealth = {
  status: "ok" | "offline";
};

export type SystemStatus = {
  llm_mode: string;
  model: string;
  embedding_model: string;
  reranker_model: string;
  chunk_size: number;
  hyde_enabled: boolean;
  total_books: number;
  total_chunks: number;
};

export type MaterialInfo = {
  /**
   * Document.id (UUID, 36 chars) — Stage 3c. Optional/empty for legacy
   * responses without a backing Document row; the frontend should prefer
   * ``id`` over ``name`` when both are present.
   */
  id?: string;
  name: string;
  sections_count: number;
  quality_label: string;
  quality_reason: string;
  /** processing | ready | error — Stage 3c Document.status. */
  status?: string;
};

export type MaterialActionResponse = {
  ok: boolean;
  message: string;
  material_name: string;
};

export type MaterialProgressResponse = {
  active: boolean;
  operation: string;
  phase: string;
  message: string;
  progress: number;
  current_file: string;
  error: string;
};

export type MaterialsResponse = {
  materials: MaterialInfo[];
};

export type SectionsResponse = {
  sections: string[];
};

export type SummaryRequest = {
  selected_file: string;
  selected_section: string;
  topic: string;
  summary_type: string;
};

export type SummaryExportRequest = {
  text: string;
  selected_file: string;
  selected_section: string;
  summary_type: string;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type ChatSource = {
  source_file: string;
  section: string;
  score: number;
  label: string;
};

export type ChatRequest = {
  message: string;
  history: ChatMessage[];
  selected_file: string;
  answer_mode: string;
};

export type TraceChunk = {
  source_file: string;
  section: string;
  chunk_id: number;
  score?: number | null;
  text_preview: string;
};

export type TraceChunkGroup = {
  item: string;
  chunks: TraceChunk[];
};

export type TraceEvent = {
  name: string;
  time_offset_sec: number;
  data: Record<string, unknown>;
};

export type TraceLLMCall = {
  elapsed_sec: number;
  prompt_chars: number;
  max_tokens?: number | null;
  output_chars: number;
  prompt_preview: string;
  output_preview: string;
};

export type TraceData = {
  kind: string;
  request: Record<string, string>;
  strategy: string;
  elapsed_sec?: number | null;
  status: string;
  events: TraceEvent[];
  chunks: Record<string, TraceChunk[] | TraceChunkGroup[]>;
  llm_calls: TraceLLMCall[];
  prompt_previews: Record<string, string>;
  output_preview: string;
  error: string;
};

export type SummaryResponse = {
  text: string;
  diagnostics: string;
  trace?: TraceData | null;
};

export type ChatResponse = {
  answer: string;
  summary: string;
  confidence_label: string;
  followup_suggestions: string[];
  history: ChatMessage[];
  sources: ChatSource[];
  diagnostics: string;
  trace?: TraceData | null;
};

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

function apiUrl(path: string): string {
  if (typeof window !== "undefined") {
    return path;
  }

  const backendUrl = process.env.BONCHMIND_API_URL ?? "http://127.0.0.1:8000";
  return `${backendUrl}${path}`;
}

/**
 * Raised by action-style calls (upload, delete, chat, …) when the backend
 * returns 401. Lets UI components show "пожалуйста, войдите" instead of a
 * generic crash. Stage 5 will wire a real redirect to /login.
 */
export class UnauthorizedError extends Error {
  constructor(message = "Войдите в систему, чтобы продолжить.") {
    super(message);
    this.name = "UnauthorizedError";
  }
}

async function fetchJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(apiUrl(path), {
      cache: "no-store",
      credentials: "include",
      headers: {
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      return fallback;
    }

    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

function ensureResponseOk(response: Response, action: string): void {
  if (response.status === 401) {
    throw new UnauthorizedError();
  }
  if (!response.ok) {
    throw new Error(`${action} failed: ${response.status}`);
  }
}

export async function getHealth(): Promise<ApiHealth> {
  return fetchJson<ApiHealth>("/api/health", { status: "offline" });
}

export async function getSystemStatus(): Promise<SystemStatus> {
  return fetchJson<SystemStatus>("/api/system/status", offlineStatus);
}

export async function getMaterials(): Promise<MaterialsResponse> {
  return fetchJson<MaterialsResponse>("/api/materials", { materials: [] });
}

export async function getMaterialSections(fileName: string): Promise<SectionsResponse> {
  return fetchJson<SectionsResponse>(`/api/materials/${encodeURIComponent(fileName)}/sections`, {
    sections: [],
  });
}

export async function getMaterialProgress(): Promise<MaterialProgressResponse> {
  return fetchJson<MaterialProgressResponse>("/api/materials/progress", {
    active: false,
    operation: "idle",
    phase: "",
    message: "",
    progress: 0,
    current_file: "",
    error: "",
  });
}

export async function uploadMaterial(file: File): Promise<MaterialActionResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/api/materials/upload", {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  ensureResponseOk(response, "Upload");
  return (await response.json()) as MaterialActionResponse;
}

export async function deleteMaterial(fileName: string): Promise<MaterialActionResponse> {
  const response = await fetch(`/api/materials/${encodeURIComponent(fileName)}`, {
    method: "DELETE",
    credentials: "include",
    headers: {
      Accept: "application/json",
    },
  });

  ensureResponseOk(response, "Delete");
  return (await response.json()) as MaterialActionResponse;
}

export async function reindexMaterial(fileName: string): Promise<MaterialActionResponse> {
  const response = await fetch(`/api/materials/${encodeURIComponent(fileName)}/reindex`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
    },
  });

  ensureResponseOk(response, "Reindex");
  return (await response.json()) as MaterialActionResponse;
}

export async function reindexLibrary(): Promise<MaterialActionResponse> {
  const response = await fetch("/api/materials/reindex", {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
    },
  });

  ensureResponseOk(response, "Reindex");
  return (await response.json()) as MaterialActionResponse;
}

export async function generateSummary(request: SummaryRequest): Promise<SummaryResponse> {
  try {
    const response = await fetch("/api/summaries", {
      method: "POST",
      credentials: "include",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    if (response.status === 401) {
      return {
        text: "Войдите в систему, чтобы сгенерировать конспект.",
        diagnostics: "",
      };
    }

    if (!response.ok) {
      return {
        text: `Ошибка API: ${response.status}`,
        diagnostics: "",
      };
    }

    return (await response.json()) as SummaryResponse;
  } catch {
    return {
      text: "Backend недоступен. Запустите python run_api.py и повторите запрос.",
      diagnostics: "",
    };
  }
}

export async function exportSummaryDocx(request: SummaryExportRequest): Promise<Blob> {
  const response = await fetch("/api/exports/summary", {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  ensureResponseOk(response, "Export");
  return await response.blob();
}

export async function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  const response = await fetch("/api/chat", {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  ensureResponseOk(response, "Chat");
  return (await response.json()) as ChatResponse;
}
