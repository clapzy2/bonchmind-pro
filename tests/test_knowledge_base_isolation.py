"""Stage 2: tests for workspace-scoped storage/index isolation in KnowledgeBase.

These tests exercise the *real* ``KnowledgeBase`` against a throwaway ChromaDB
collection (created in ``tmp_path``). To avoid loading the heavy embedding /
reranker models in CI, the instance is built with ``__new__`` (skipping
``__init__``) and wired up with a tiny deterministic fake embedder.
"""
import hashlib

import chromadb

import config
from src.knowledge_base import KnowledgeBase


class FakeEmbeddings:
    """Deterministic, dependency-free stand-in for the BGE-M3 embeddings."""

    def __init__(self, dim=16):
        self.dim = dim

    def _vec(self, text):
        digest = hashlib.md5(text.strip().encode("utf-8")).digest()
        repeats = (self.dim // len(digest)) + 1
        raw = (digest * repeats)[: self.dim]
        vec = [b / 255.0 for b in raw]
        norm = sum(v * v for v in vec) ** 0.5
        if norm == 0:
            return vec
        return [v / norm for v in vec]

    def embed_documents(self, texts):
        return [self._vec(text) for text in texts]

    def embed_query(self, text):
        return self._vec(text)


def make_kb(tmp_path):
    kb = KnowledgeBase.__new__(KnowledgeBase)
    kb._log = lambda *args, **kwargs: None
    kb._llm = None
    kb._reranker = None
    kb._reranker_loaded = True  # skip loading the cross-encoder
    kb._embeddings = FakeEmbeddings()

    client = chromadb.PersistentClient(path=str(tmp_path / "chromadb"))
    kb._client = client
    kb._col = client.create_collection(
        name=config.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return kb


def write_doc(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_chunk_id_differs_across_workspaces_for_same_text():
    """Stage 3c: _chunk_id is now (workspace_id, document_id, text)."""
    same_text = "Один и тот же фрагмент текста для двух разных рабочих пространств."

    id_a = KnowledgeBase._chunk_id("workspace-a", "doc-1", same_text)
    id_b = KnowledgeBase._chunk_id("workspace-b", "doc-1", same_text)

    assert id_a != id_b
    # Stable for repeated calls with the same arguments.
    assert id_a == KnowledgeBase._chunk_id("workspace-a", "doc-1", same_text)


def test_chunk_id_differs_across_documents_for_same_text_in_one_workspace():
    """Replace-on-conflict relies on chunk_id changing when document_id does."""
    same_text = "Замена документа должна получить новые ID чанков."

    id_old = KnowledgeBase._chunk_id("workspace-a", "doc-old", same_text)
    id_new = KnowledgeBase._chunk_id("workspace-a", "doc-new", same_text)

    assert id_old != id_new


def test_add_book_stores_original_name_as_source_file(tmp_path):
    """Stage 3d fix: source_file metadata is the user-facing original_name.

    Authenticated uploads land on disk at
    ``docs/<workspace>/<document_id>__<original_name>``, but Chroma chunks
    must record ``source_file = original_name`` so:

    * ``list_materials`` can look up profile by ``Document.original_name``
      (which surfaced the smoke-test bug — KB returned 0 chunks because it
      was looking for ``alice_doc.txt`` while metadata held
      ``<uuid>__alice_doc.txt``);
    * chat source labels show ``alice_doc.txt -> Раздел`` instead of
      ``13606847-...__alice_doc.txt -> Раздел``.
    """
    kb = make_kb(tmp_path)
    text = "Содержимое для проверки имени source_file. " * 5

    document_id = "doc-uuid-1234"
    on_disk = write_doc(tmp_path, f"{document_id}__alice_doc.txt", text)

    kb.add_book(
        on_disk,
        workspace_id="workspace-a",
        document_id=document_id,
        original_name="alice_doc.txt",
    )

    # The KB profile look-up by original_name now returns non-zero counts.
    profile = kb.get_file_profile("alice_doc.txt", workspace_id="workspace-a")
    assert profile["chunk_count"] > 0

    # Files listing surfaces the user-facing name (no UUID prefix).
    files = kb.get_available_files(workspace_id="workspace-a")
    assert files == ["alice_doc.txt"]


def test_add_book_falls_back_to_filename_when_original_name_missing(tmp_path):
    """Legacy/Gradio path: no ``original_name`` -> source_file is the
    on-disk basename (unchanged Stage 2 behaviour)."""
    kb = make_kb(tmp_path)
    on_disk = write_doc(tmp_path, "legacy_book.txt", "Минимальный материал. " * 5)

    kb.add_book(on_disk, workspace_id="workspace-legacy")

    files = kb.get_available_files(workspace_id="workspace-legacy")
    assert files == ["legacy_book.txt"]


def test_add_book_same_text_indexed_independently_per_workspace(tmp_path):
    kb = make_kb(tmp_path)
    text = "Содержимое учебника одинаково для обоих пространств. " * 5

    doc_a = write_doc(tmp_path, "book_a.txt", text)
    doc_b = write_doc(tmp_path, "book_b.txt", text)

    result_a = kb.add_book(doc_a, workspace_id="workspace-a")
    result_b = kb.add_book(doc_b, workspace_id="workspace-b")

    assert result_a.startswith("✅")
    assert result_b.startswith("✅")

    stats_a = kb.stats(workspace_id="workspace-a")
    stats_b = kb.stats(workspace_id="workspace-b")

    assert stats_a["total_chunks"] > 0
    assert stats_b["total_chunks"] > 0
    # Indexing the same text in another workspace must not be skipped as a
    # "duplicate" of workspace-a's chunks.
    assert stats_a["total_chunks"] == stats_b["total_chunks"]


def test_listing_and_stats_are_scoped_to_workspace(tmp_path):
    kb = make_kb(tmp_path)

    doc_a = write_doc(tmp_path, "alpha.txt", "Материал рабочего пространства A. " * 5)
    doc_b = write_doc(tmp_path, "beta.txt", "Материал рабочего пространства B. " * 5)

    kb.add_book(doc_a, workspace_id="workspace-a")
    kb.add_book(doc_b, workspace_id="workspace-b")

    files_a = kb.get_available_files(workspace_id="workspace-a")
    files_b = kb.get_available_files(workspace_id="workspace-b")

    assert files_a == ["alpha.txt"]
    assert files_b == ["beta.txt"]

    stats_a = kb.stats(workspace_id="workspace-a")
    stats_b = kb.stats(workspace_id="workspace-b")

    assert stats_a["books"] == ["alpha.txt"]
    assert stats_b["books"] == ["beta.txt"]

    chunks_a = kb.get_file_chunks(workspace_id="workspace-a")
    chunks_b = kb.get_file_chunks(workspace_id="workspace-b")

    assert all(chunk["source_file"] == "alpha.txt" for chunk in chunks_a)
    assert all(chunk["source_file"] == "beta.txt" for chunk in chunks_b)


def test_search_with_sources_does_not_leak_across_workspaces(tmp_path):
    kb = make_kb(tmp_path)

    text_a = "Уникальный текст про рабочее пространство Альфа. " * 5
    text_b = "Уникальный текст про рабочее пространство Бета. " * 5

    doc_a = write_doc(tmp_path, "alpha.txt", text_a)
    doc_b = write_doc(tmp_path, "beta.txt", text_b)

    kb.add_book(doc_a, workspace_id="workspace-a")
    kb.add_book(doc_b, workspace_id="workspace-b")

    _, sources_a = kb.search_with_sources(text_a, workspace_id="workspace-a")
    _, sources_b = kb.search_with_sources(text_a, workspace_id="workspace-b")

    assert sources_a, "expected workspace-a search to find its own chunk"
    assert all(src["source_file"] == "alpha.txt" for src in sources_a)
    # Searching workspace-b for workspace-a's text must never surface
    # workspace-a's chunks.
    assert all(src["source_file"] != "alpha.txt" for src in sources_b)


def test_remove_book_only_affects_its_own_workspace(tmp_path):
    kb = make_kb(tmp_path)

    text = "Общий текст материала, который потом удалят. " * 5
    doc_a = write_doc(tmp_path, "shared.txt", text)
    doc_b = write_doc(tmp_path, "shared.txt", text)

    kb.add_book(doc_a, workspace_id="workspace-a")
    kb.add_book(doc_b, workspace_id="workspace-b")

    kb.remove_book("shared.txt", workspace_id="workspace-a")

    assert kb.get_available_files(workspace_id="workspace-a") == []
    assert kb.get_available_files(workspace_id="workspace-b") == ["shared.txt"]


def test_clear_only_affects_its_own_workspace(tmp_path):
    kb = make_kb(tmp_path)

    doc_a = write_doc(tmp_path, "alpha.txt", "Материал A для очистки. " * 5)
    doc_b = write_doc(tmp_path, "beta.txt", "Материал B остаётся. " * 5)

    kb.add_book(doc_a, workspace_id="workspace-a")
    kb.add_book(doc_b, workspace_id="workspace-b")

    kb.clear(workspace_id="workspace-a")

    assert kb.get_available_files(workspace_id="workspace-a") == []
    assert kb.get_available_files(workspace_id="workspace-b") == ["beta.txt"]
    assert kb.stats(workspace_id="workspace-b")["total_chunks"] > 0


def test_search_chunks_for_summary_falls_back_to_workspace_chunks_when_pools_empty(tmp_path, monkeypatch):
    """Regression guard for the Stage 6 smoke bug.

    When semantic + lexical pools both come back empty (e.g. short English
    queries like "Wi-Fi" against a Russian-language scorer, or
    Chroma-version quirks where the keyword search yields nothing) the
    summary path used to return ``[]``, leaving the user with "тема не
    найдена" even though Assistant (which has its own fallback) found the
    same material. ``search_chunks_for_summary`` now mirrors
    ``search_with_sources`` and falls back to whatever chunks the
    workspace + file_filter combination owns.
    """
    kb = make_kb(tmp_path)
    text = (
        "Wi-Fi - стандарт беспроводных локальных сетей.\n"
        "Wi-Fi работает в полосе 2.4 GHz и 5 GHz.\n"
    )
    kb.add_book(
        write_doc(tmp_path, "wifi.txt", text),
        workspace_id="workspace-a",
        document_id="doc-wifi",
        original_name="wifi.txt",
    )

    # Force the regular semantic + lexical pipelines to return empty so
    # the test exercises the fallback alone. This is the user's
    # observed symptom, not a contrived state — semantic returning [] is
    # how the live bug manifests.
    monkeypatch.setattr(kb, "_raw_search", lambda *_a, **_kw: [])
    monkeypatch.setattr(
        kb,
        "_lexical_candidates_for_summary",
        lambda *_a, **_kw: [],
    )

    chunks = kb.search_chunks_for_summary(
        query="Wi-Fi",
        file_filter="all",
        section_filter=None,
        top_k=18,
        workspace_id="workspace-a",
    )

    assert chunks, "fallback must surface the workspace's chunks"
    assert all(c["source_file"] == "wifi.txt" for c in chunks)


def test_search_chunks_for_summary_fallback_stays_inside_caller_workspace(tmp_path, monkeypatch):
    """Belt-and-braces: the fallback must never leak chunks from another
    workspace. Stage 3+ isolation invariants apply to the fallback path
    too."""
    kb = make_kb(tmp_path)
    kb.add_book(
        write_doc(tmp_path, "alice.txt", "Документ Alice про Wi-Fi сети. " * 3),
        workspace_id="workspace-a",
        document_id="doc-alice",
        original_name="alice.txt",
    )
    kb.add_book(
        write_doc(tmp_path, "bob.txt", "Документ Bob про Bluetooth. " * 3),
        workspace_id="workspace-b",
        document_id="doc-bob",
        original_name="bob.txt",
    )

    monkeypatch.setattr(kb, "_raw_search", lambda *_a, **_kw: [])
    monkeypatch.setattr(
        kb,
        "_lexical_candidates_for_summary",
        lambda *_a, **_kw: [],
    )

    chunks_a = kb.search_chunks_for_summary(
        query="anything",
        file_filter="all",
        section_filter=None,
        top_k=18,
        workspace_id="workspace-a",
    )
    chunks_b = kb.search_chunks_for_summary(
        query="anything",
        file_filter="all",
        section_filter=None,
        top_k=18,
        workspace_id="workspace-b",
    )

    assert chunks_a and all(c["source_file"] == "alice.txt" for c in chunks_a)
    assert chunks_b and all(c["source_file"] == "bob.txt" for c in chunks_b)
    files_a = {c["source_file"] for c in chunks_a}
    files_b = {c["source_file"] for c in chunks_b}
    assert files_a.isdisjoint(files_b)
