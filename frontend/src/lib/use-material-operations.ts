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
  // Multi-file upload (Stage 11): the frontend drives N single-file uploads
  // sequentially through the existing endpoint. ``batch`` is non-null only
  // while a multi-upload queue is in flight; it carries the position so the UI
  // can show "Файл 2 из 5".
  const [batch, setBatch] = useState<{ index: number; total: number } | null>(null);
  const pendingRef = useRef<{ onComplete?: (name: string) => void; materialName: string } | null>(null);
  // Aborts the in-flight upload POST so "Отменить" can stop a large file mid
  // transfer (before the backend even queues the indexing job).
  const abortRef = useRef<AbortController | null>(null);
  // Set by ``cancel`` so the sequential ``uploadFiles`` loop stops after the
  // current file instead of marching through the rest of the queue.
  const batchCancelledRef = useRef(false);
  // Guards against setState after the screen unmounts mid-batch (e.g. a tab
  // switch): the imperative loop checks this before touching state.
  const mountedRef = useRef(true);

  const isRunning = activeOperation !== null || batch !== null;

  // Poll progress while an operation is in flight. Interval is cleared on
  // unmount and whenever activeOperation changes, so it never leaks.
  useEffect(() => {
    if (activeOperation === null) {
      return;
    }

    let cancelled = false;

    async function poll() {
      const response = await getMaterialProgress();
      if (cancelled) {
        return;
      }
      // Ignore the pristine idle snapshot (active=false, phase=""): the backend
      // hasn't queued the job yet — e.g. a large file is still transferring.
      // Overwriting the optimistic "active" state here is what made the
      // progress bar / cancel button vanish until the upload finished.
      if (!response.active && response.phase === "") {
        return;
      }
      setProgress(response);
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
      abortRef.current = null;
      setActiveOperation(null);
      setCancelling(false);
    }

    finalize().catch(() => {
      pendingRef.current = null;
      abortRef.current = null;
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

  // Track mount state so the imperative ``uploadFiles`` loop never setState on
  // an unmounted screen (a tab switch unmounts this hook).
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const cancel = useCallback(async () => {
    setCancelling(true);
    // Stop the sequential multi-upload queue after the current file.
    batchCancelledRef.current = true;
    setNotice({ tone: "info", text: "Отменяю операцию…" });
    // Abort the in-flight upload POST (stops a large file mid-transfer); the
    // run() catch turns the AbortError into a cancelled state.
    abortRef.current?.abort();
    try {
      // Also ask the backend to cancel the indexing job if it already started.
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
        // Cancelled mid-transfer via AbortController → treat as a cancel, not
        // an error. The backend never queued a job, so nothing to roll back.
        if (err instanceof DOMException && err.name === "AbortError") {
          setNotice({ tone: "info", text: `Загрузка ${args.currentFile ?? ""} отменена.` });
          setProgress({
            active: false,
            operation: "idle",
            phase: "cancelled",
            message: `Загрузка ${args.currentFile ?? ""} отменена.`,
            progress: 100,
            current_file: args.currentFile ?? "",
            error: "",
          });
          pendingRef.current = null;
          setActiveOperation(null);
          setCancelling(false);
          return;
        }
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
    (file: File, onComplete?: (materialName: string) => void) => {
      const controller = new AbortController();
      abortRef.current = controller;
      return run({
        operation: "upload",
        currentFile: file.name,
        queuedMessage: `Ставлю в очередь загрузку ${file.name}`,
        startNotice: {
          tone: "info",
          text: `Загружаю и индексирую ${file.name}. После этого материал появится в библиотеке.`,
        },
        errorText: "Не удалось загрузить материал. Проверьте backend и повторите попытку.",
        call: () => uploadMaterial(file, controller.signal),
        onComplete,
      });
    },
    [run],
  );

  // Multi-file upload (Stage 11). Drives the files through the existing
  // single-file endpoint one at a time — no backend change, every file keeps
  // its own size limit / replace-on-conflict / audit. A failed file doesn't
  // abort the queue; cancel stops after the current file.
  const uploadFiles = useCallback(
    async (files: File[], onComplete?: (materialName: string) => void) => {
      if (isRunning || files.length === 0) {
        return;
      }
      batchCancelledRef.current = false;
      setCancelling(false);
      setNotice(null);

      const total = files.length;
      let ok = 0;
      let failed = 0;
      let lastOkName = "";

      // Resolve once the *current* file's background job settles. Guards against
      // the stale-progress race: don't accept a "done" snapshot until we've seen
      // this file's job go active, unless the snapshot's current_file matches
      // (a fast finish we'd otherwise miss between polls).
      const pollUntilSettled = (label: string, expectedNames: string[]) =>
        new Promise<MaterialProgressResponse>((resolve) => {
          let seenActive = false;
          let timer = 0;
          const schedule = () => {
            timer = window.setTimeout(tick, 500);
          };
          function tick() {
            if (!mountedRef.current) {
              resolve(idleMaterialProgress);
              return;
            }
            getMaterialProgress()
              .then((snap) => {
                // Pristine idle: the job isn't queued yet (file still
                // transferring). Keep waiting.
                if (!snap.active && snap.phase === "") {
                  schedule();
                  return;
                }
                setProgress({
                  ...snap,
                  message: snap.message ? `${label}: ${snap.message}` : label,
                });
                if (snap.active) {
                  seenActive = true;
                  schedule();
                  return;
                }
                if (snap.phase === "cancelled") {
                  resolve(snap);
                  return;
                }
                const settledForThisFile =
                  (snap.phase === "done" || snap.phase === "error") &&
                  expectedNames.includes(snap.current_file);
                if (seenActive || settledForThisFile) {
                  resolve(snap);
                  return;
                }
                // Stale "done" from the previous file, or the job hasn't started
                // yet — keep waiting for this file's own run.
                schedule();
              })
              .catch(() => schedule());
          }
          window.clearTimeout(timer);
          timer = window.setTimeout(tick, 300);
        });

      setBatch({ index: 0, total });

      for (let i = 0; i < total; i++) {
        if (batchCancelledRef.current || !mountedRef.current) {
          break;
        }
        const file = files[i];
        const label = total > 1 ? `Файл ${i + 1} из ${total}` : `Загрузка ${file.name}`;
        setBatch({ index: i, total });
        setProgress({
          active: true,
          operation: "upload",
          phase: "queued",
          message: `${label}: ${file.name}`,
          progress: 0,
          current_file: file.name,
          error: "",
        });

        const controller = new AbortController();
        abortRef.current = controller;

        try {
          const response = await uploadMaterial(file, controller.signal);
          if (!response.ok) {
            failed++;
            continue;
          }
          const settled = await pollUntilSettled(label, [file.name, response.material_name].filter(Boolean));
          if (settled.phase === "cancelled") {
            break;
          }
          if (settled.phase === "error") {
            failed++;
          } else {
            ok++;
            lastOkName = response.material_name || file.name;
            // Refresh the library now so each file appears as it finishes,
            // instead of the whole batch popping in at the very end (which
            // looked like "shows 2 but only 1 loaded" mid-queue).
            if (mountedRef.current) {
              await Promise.resolve(onSync()).catch(() => undefined);
            }
          }
        } catch (err) {
          // Aborted mid-transfer (cancel) → stop the whole queue.
          if (err instanceof DOMException && err.name === "AbortError") {
            break;
          }
          if (handleAuthError(err, router)) {
            abortRef.current = null;
            setBatch(null);
            setProgress(idleMaterialProgress);
            return;
          }
          failed++;
        }
      }

      abortRef.current = null;
      if (!mountedRef.current) {
        return;
      }
      setBatch(null);
      setProgress(idleMaterialProgress);
      setCancelling(false);

      await onSync();
      if (!mountedRef.current) {
        return;
      }

      const cancelled = batchCancelledRef.current;
      const parts: string[] = [];
      if (ok > 0) parts.push(`загружено ${ok}`);
      if (failed > 0) parts.push(`с ошибкой ${failed}`);
      const summary = parts.length ? parts.join(", ") : "ничего не загружено";
      setNotice({
        tone: cancelled ? "info" : failed > 0 ? "warning" : "success",
        text: cancelled ? `Загрузка остановлена: ${summary}.` : `Готово: ${summary}.`,
      });

      // Auto-select the last successfully indexed material (never after cancel).
      if (!cancelled && ok > 0 && lastOkName && onComplete) {
        onComplete(lastOkName);
      }
    },
    [isRunning, onSync, router],
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
    batch,
    uploadFile,
    uploadFiles,
    deleteFile,
    reindexFile,
    reindexAll,
    cancel,
  };
}
