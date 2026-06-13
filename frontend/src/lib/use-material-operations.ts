"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  cancelMaterialOperation,
  deleteMaterial,
  getMaterialProgress,
  reindexLibrary,
  reindexMaterial,
  uploadMaterial,
  type MaterialActionResponse,
  type MaterialProgressResponse,
} from "@/lib/api";
import { handleAuthError } from "@/lib/handle-auth-error";

/**
 * Shared lifecycle for every long-running material operation: upload,
 * delete, reindex-one, reindex-all. Stage 7c extracted this out of
 * ``materials-workspace`` so the Assistant and Summary screens can offer an
 * inline upload (the paperclip) without re-implementing the polling /
 * finalize / sync dance three times.
 *
 * Lifecycle for one operation:
 *
 * 1. ``run`` sets ``activeOperation`` and an optimistic ``active: true``
 *    progress snapshot, then fires the POST.
 * 2. While ``activeOperation`` is set, a 500 ms poll mirrors
 *    ``/api/materials/progress`` into ``progress``. The interval is always
 *    cleared on unmount or when the operation ends.
 * 3. When the poll reports ``active: false``, the finalize effect calls
 *    ``onSync`` (the caller refreshes its material list), then fires the
 *    operation's ``onComplete`` with the canonical material name so the
 *    caller can auto-select the freshly indexed file.
 *
 * F5 during an operation IS resumed (Stage 9a upload-ux): on mount the hook
 * probes ``/api/materials/progress`` once and, if the workspace has an active
 * job, reattaches to it (the progress bar continues, the list refreshes when
 * it finishes). ``cancel`` requests cooperative cancellation of the running
 * job; the poll then reflects the cancelled state.
 */

const RESUMABLE_OPERATIONS: ReadonlyArray<RunArgs["operation"]> = [
  "upload",
  "delete",
  "reindex_material",
  "reindex_library",
];

function isResumableOperation(operation: string): operation is RunArgs["operation"] {
  return (RESUMABLE_OPERATIONS as readonly string[]).includes(operation);
}

export type MaterialOperationNotice = {
  tone: "info" | "warning" | "success";
  text: string;
};

export const idleMaterialProgress: MaterialProgressResponse = {
  active: false,
  operation: "idle",
  phase: "",
  message: "",
  progress: 0,
  current_file: "",
  error: "",
};

type RunArgs = {
  operation: "upload" | "delete" | "reindex_material" | "reindex_library";
  currentFile?: string;
  queuedMessage: string;
  startNotice?: MaterialOperationNotice;
  errorText: string;
  call: () => Promise<MaterialActionResponse>;
  onComplete?: (materialName: string) => void;
};

type UseMaterialOperationsArgs = {
  /** Refresh the caller's material list. Awaited before ``onComplete``. */
  onSync: () => Promise<void> | void;
};

export function useMaterialOperations({ onSync }: UseMaterialOperationsArgs) {
  const router = useRouter();
  const [progress, setProgress] = useState<MaterialProgressResponse>(idleMaterialProgress);
  const [notice, setNotice] = useState<MaterialOperationNotice | null>(null);
  const [activeOperation, setActiveOperation] = useState<RunArgs["operation"] | null>(null);
  // Immediate "cancel requested" flag for responsive UI — the real stop still
  // happens at the next batch checkpoint on the backend.
  const [cancelling, setCancelling] = useState(false);
  const pendingRef = useRef<{ onComplete?: (name: string) => void; materialName: string } | null>(null);

  const isRunning = activeOperation !== null;

  // Poll progress while an operation is in flight. Interval is cleared on
  // unmount and whenever activeOperation changes, so it never leaks.
  useEffect(() => {
    if (activeOperation === null) {
      return;
    }

    let cancelled = false;

    async function poll() {
      const response = await getMaterialProgress();
      if (!cancelled) {
        setProgress(response);
      }
    }

    poll().catch(() => undefined);
    const timer = window.setInterval(() => {
      poll().catch(() => undefined);
    }, 500);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeOperation]);

  // Finalize once the backend job flips active=false: refresh the caller's
  // list, then auto-select the new material.
  useEffect(() => {
    if (activeOperation === null || progress.active) {
      return;
    }

    let cancelled = false;

    async function finalize() {
      await onSync();
      if (cancelled) {
        return;
      }

      const pending = pendingRef.current;
      const isCancelled = progress.phase === "cancelled";
      const ok = progress.phase !== "error" && !isCancelled;

      setNotice({
        tone: isCancelled ? "info" : ok ? "success" : "warning",
        text:
          progress.message ||
          (isCancelled
            ? "Операция отменена."
            : ok
              ? "Операция с библиотекой завершена."
              : "Операция с библиотекой завершилась с ошибкой."),
      });

      // Only auto-select on a successful finish — never after error/cancel.
      if (ok && pending?.onComplete && pending.materialName) {
        pending.onComplete(pending.materialName);
      }

      pendingRef.current = null;
      setActiveOperation(null);
      setCancelling(false);
    }

    finalize().catch(() => {
      pendingRef.current = null;
      setActiveOperation(null);
      setCancelling(false);
    });

    return () => {
      cancelled = true;
    };
  }, [activeOperation, progress, onSync]);

  // Resume an in-flight job after F5 (Stage 9a upload-ux): probe the server's
  // per-workspace progress once on mount and reattach if something is active.
  // No onComplete after a reload (we can't recover the original callback) — the
  // list just refreshes when the job finishes.
  useEffect(() => {
    let cancelled = false;
    getMaterialProgress()
      .then((snapshot) => {
        if (cancelled || !snapshot.active || !isResumableOperation(snapshot.operation)) {
          return;
        }
        pendingRef.current = null;
        // External-system (server progress) reattach, not derived render state.
        setProgress(snapshot);
        setActiveOperation(snapshot.operation);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const cancel = useCallback(async () => {
    setCancelling(true);
    setNotice({ tone: "info", text: "Отменяю операцию…" });
    try {
      await cancelMaterialOperation();
    } catch (err) {
      if (handleAuthError(err, router)) {
        return;
      }
      // Other errors are non-fatal — the poll reflects the real state.
    }
  }, [router]);

  const run = useCallback(
    async (args: RunArgs) => {
      if (activeOperation !== null) {
        return;
      }

      setActiveOperation(args.operation);
      pendingRef.current = { onComplete: args.onComplete, materialName: args.currentFile ?? "" };
      setProgress({
        active: true,
        operation: args.operation,
        phase: "queued",
        message: args.queuedMessage,
        progress: 0,
        current_file: args.currentFile ?? "",
        error: "",
      });
      setNotice(args.startNotice ?? { tone: "info", text: args.queuedMessage });

      try {
        const response = await args.call();
        if (!response.ok) {
          setNotice({ tone: "warning", text: response.message });
          setProgress(idleMaterialProgress);
          pendingRef.current = null;
          setActiveOperation(null);
          return;
        }

        // Prefer the backend's canonical material_name for auto-select; the
        // upload endpoint may normalize the uploaded file name.
        pendingRef.current = {
          onComplete: args.onComplete,
          materialName: response.material_name || args.currentFile || "",
        };
        setNotice({ tone: "info", text: response.message });
        // Snapshot progress now; the polling + finalize effects take over.
        setProgress(await getMaterialProgress());
      } catch (err) {
        if (handleAuthError(err, router)) {
          return;
        }
        setNotice({ tone: "warning", text: args.errorText });
        setProgress({
          active: false,
          operation: "idle",
          phase: "error",
          message: args.errorText,
          progress: 100,
          current_file: args.currentFile ?? "",
          error: `${args.operation}_failed`,
        });
        pendingRef.current = null;
        setActiveOperation(null);
      }
    },
    [activeOperation, router],
  );

  const uploadFile = useCallback(
    (file: File, onComplete?: (materialName: string) => void) =>
      run({
        operation: "upload",
        currentFile: file.name,
        queuedMessage: `Ставлю в очередь загрузку ${file.name}`,
        startNotice: {
          tone: "info",
          text: `Загружаю и индексирую ${file.name}. После этого материал появится в библиотеке.`,
        },
        errorText: "Не удалось загрузить материал. Проверьте backend и повторите попытку.",
        call: () => uploadMaterial(file),
        onComplete,
      }),
    [run],
  );

  const deleteFile = useCallback(
    (materialName: string) =>
      run({
        operation: "delete",
        currentFile: materialName,
        queuedMessage: `Ставлю в очередь удаление ${materialName}`,
        startNotice: { tone: "info", text: `Удаляю ${materialName} из библиотеки и векторной базы.` },
        errorText: "Не удалось удалить материал. Попробуйте еще раз после проверки backend.",
        call: () => deleteMaterial(materialName),
      }),
    [run],
  );

  const reindexFile = useCallback(
    (materialName: string) =>
      run({
        operation: "reindex_material",
        currentFile: materialName,
        queuedMessage: `Ставлю в очередь переиндексацию ${materialName}`,
        startNotice: {
          tone: "info",
          text: `Переиндексирую ${materialName}. Это полезно после замены файла или очистки структуры.`,
        },
        errorText: "Не удалось переиндексировать материал.",
        call: () => reindexMaterial(materialName),
      }),
    [run],
  );

  const reindexAll = useCallback(
    () =>
      run({
        operation: "reindex_library",
        queuedMessage: "Ставлю в очередь полную пересборку библиотеки",
        startNotice: {
          tone: "info",
          text: "Полностью пересобираю библиотеку из папки docs. Это может занять немного времени.",
        },
        errorText: "Не удалось переиндексировать библиотеку целиком.",
        call: () => reindexLibrary(),
      }),
    [run],
  );

  return {
    progress,
    notice,
    setNotice,
    isRunning,
    activeOperation,
    cancelling,
    uploadFile,
    deleteFile,
    reindexFile,
    reindexAll,
    cancel,
  };
}
