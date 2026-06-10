"""Workspace-scoped file storage helpers (Stage 2: workspace-scoping).

All user-uploaded materials live under ``docs/<workspace_id>/`` instead of a
single shared ``docs/`` directory. This module centralizes the helpers needed
to build and validate those paths so ``KnowledgeBase`` and the service layer
agree on a single layout.

Filenames remain the addressing key within a workspace (per the accepted
Stage 1/2 decisions); a future stage may switch to ``<document_id>__<name>``
once the ``Document`` table is the source of truth for stored paths.
"""

from __future__ import annotations

import glob
import os
import re

import config


# Characters that are not safe to use verbatim in a filename on disk
# (path separators, drive letters, NUL, etc.).
_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

_MAX_NAME_LENGTH = 200


def sanitize_filename(name: str) -> str:
    """Return a filesystem-safe version of ``name``.

    Strips directory components, removes ``..`` traversal sequences and any
    characters that are unsafe on common filesystems, and caps the length.
    Falls back to ``"file"`` if nothing usable remains.
    """
    candidate = os.path.basename(str(name or "").strip())
    candidate = candidate.replace("..", "")
    candidate = _UNSAFE_CHARS.sub("_", candidate)
    candidate = candidate.strip(" .")

    if not candidate:
        return "file"

    if len(candidate) > _MAX_NAME_LENGTH:
        root, ext = os.path.splitext(candidate)
        candidate = root[: max(1, _MAX_NAME_LENGTH - len(ext))] + ext

    return candidate


def workspace_docs_dir(workspace_id: str) -> str:
    """Return ``docs/<workspace_id>/`` (sanitizing ``workspace_id`` itself)."""
    safe_workspace_id = sanitize_filename(workspace_id)
    return os.path.join(config.DOCS_DIR, safe_workspace_id)


def document_stored_path(workspace_id: str, original_name: str) -> str:
    """Return the on-disk path for ``original_name`` within ``workspace_id``."""
    return os.path.join(workspace_docs_dir(workspace_id), sanitize_filename(original_name))


def is_workspace_library_path(file_path: str, workspace_id: str) -> bool:
    """True if ``file_path`` is a top-level file inside ``docs/<workspace_id>/``.

    Mirrors the previous single-tenant check (``KnowledgeBase._is_library_file_path``)
    but scopes it to one workspace's directory, and rejects files in nested
    subdirectories of that workspace.
    """
    if not file_path:
        return False

    base_dir = os.path.normcase(os.path.abspath(workspace_docs_dir(workspace_id)))
    normalized_path = os.path.normcase(os.path.abspath(file_path))

    try:
        common = os.path.commonpath([base_dir, normalized_path])
    except ValueError:
        return False

    if common != base_dir:
        return False

    relative = os.path.relpath(normalized_path, base_dir)
    if relative.startswith(".."):
        return False

    return os.path.dirname(relative) in ("", ".")


def iter_workspace_library_files(workspace_id: str):
    """Return sorted absolute paths of supported files in ``docs/<workspace_id>/``."""
    docs_dir = workspace_docs_dir(workspace_id)
    os.makedirs(docs_dir, exist_ok=True)

    files = []
    for ext in config.SUPPORTED_FORMATS:
        files.extend(glob.glob(os.path.join(docs_dir, f"*{ext}")))

    return sorted(
        {
            os.path.abspath(file_path)
            for file_path in files
            if is_workspace_library_path(file_path, workspace_id)
        }
    )
