"""
knowledge_base.py - загрузка файлов, разбивка на разделы, индексация, поиск.
Основной модуль RAG-пайплайна.
"""
import os
import re
import gc
import hashlib
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src import storage
from src.document_loader import load_file
from src.text_processing import clean_sections, detect_sections, get_splitter, is_user_visible_section


class IndexingCancelled(RuntimeError):
    """Raised inside ``add_book`` when a ``cancel_check`` requests cancellation
    (Stage 9a). The caller is responsible for rolling back partial state."""


# Основной класс - База Знаний

class KnowledgeBase:
    """Управляет загрузкой, индексацией и поиском по текстам."""

    def __init__(self, progress_callback=None, llm_engine=None):
        self._log = progress_callback or print
        self._reranker = None
        self._reranker_loaded = False
        self._llm = llm_engine
        self._init_embeddings()
        self._init_db()

    def _init_embeddings(self):
        """Загружаем модель BGE-M3 для превращения текста в вектор."""
        self._log("Загружаем embedding-модель...")
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError:
            from langchain_community.embeddings import HuggingFaceEmbeddings
        self._embeddings = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL,
            model_kwargs={"device": config.EMBEDDING_DEVICE},
            encode_kwargs={"normalize_embeddings": True},
        )
        self._log(f"Эмбеддинги загружены: {config.EMBEDDING_MODEL}")

    def _init_db(self):
        """Подключаемся к ChromaDB (создаём коллекцию, если нет)."""
        import chromadb
        os.makedirs(config.CHROMA_DIR, exist_ok=True)
        self._client = chromadb.PersistentClient(path=config.CHROMA_DIR)
        try:
            self._col = self._client.get_collection(config.COLLECTION_NAME)
            self._log(f"Коллекция: {self._col.count()} фрагментов")
        except Exception:
            self._col = self._client.create_collection(
                name=config.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            self._log("Новая коллекция создана")

    def _ensure_reranker(self):
        """Загружаем реранкер при первом использовании (ленивая загрузка)."""
        if self._reranker_loaded:
            return
        self._reranker_loaded = True
        if not config.USE_RERANKER:
            return
        try:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder(config.RERANKER_MODEL)
            self._log(f"Reranker: {config.RERANKER_MODEL}")
        except Exception as e:
            self._log(f"Reranker недоступен: {e}")

    def set_llm(self, llm_engine):
        self._llm = llm_engine

    def _get_llm(self):
        if self._llm is None:
            from src.llm_engine import LLMEngine
            self._llm = LLMEngine()
        return self._llm

    @staticmethod
    def _md5(text):
        """Хеш текста для проверки дубликатов внутри одного запроса/выдачи."""
        return hashlib.md5(text.strip().encode()).hexdigest()

    @staticmethod
    def _chunk_id(workspace_id, document_id, text):
        """ID чанка в ChromaDB: уникален в пределах workspace+документа.

        Stage 3c заменяет ``source_file`` на ``document_id`` (UUID из таблицы
        ``Document``) во входе хеша. ``document_id`` стабилен на протяжении
        жизни записи, поэтому ID чанка устойчив к будущему переименованию
        ``original_name`` и к замене документа (новая запись получает
        независимый набор chunk-ID).
        """
        raw = f"{workspace_id}:{document_id}:{text.strip()}"
        return hashlib.md5(raw.encode()).hexdigest()

    # Индексация файла
    def add_book(
        self,
        file_path,
        *,
        workspace_id,
        document_id=None,
        original_name=None,
        progress_callback=None,
        cancel_check=None,
    ):
        """Загрузить файл, разбить на чанки, добавить в ChromaDB.

        ``document_id`` — UUID записи ``Document`` (Stage 3c). Когда метод
        вызывается из legacy/Gradio-пути без записи ``Document``, передаётся
        ``None`` и ``document_id`` подставляется как ``original_filename``,
        чтобы сохранить старое поведение дедупликации по имени файла.

        ``original_name`` — пользовательское имя материала (например
        ``alice_doc.txt``). На диске файл может лежать под именем с
        document_id-префиксом (``<uuid>__alice_doc.txt``), но в Chroma
        metadata ``source_file`` сохраняется как ``original_name``, чтобы:

        * ``list_materials`` / ``list_sections`` находили чанки по тому же
          ключу, что отдаётся фронту (``Document.original_name``);
        * метки источников в чате (``source_file -> section``) показывали
          пользователю понятное имя, а не UUID-префикс.

        Если ``original_name`` не передан, fallback — ``os.path.basename(file_path)``
        (Gradio / прямые тесты KB без service-слоя).
        """
        def report(**payload):
            if progress_callback:
                progress_callback(**payload)

        filename = os.path.basename(file_path)
        # Legacy bridge: anonymous Gradio uploads identify the document by
        # filename, while Stage 3c authenticated uploads pass an explicit UUID.
        effective_document_id = document_id or filename
        effective_source_name = original_name or filename

        lower = file_path.lower()
        supported = any(lower.endswith(fmt) for fmt in config.SUPPORTED_FORMATS)
        if not supported:
            return f"Формат не поддерживается: {filename}"

        report(phase="reading", progress=5, message=f"Читаю {filename}", current_file=filename)
        self._log(f"Обрабатываем: {filename}")
        try:
            raw = load_file(file_path)
        except Exception as e:
            return f"Ошибка чтения {filename}: {e}"
        if not raw.strip():
            return f"Файл пуст: {filename}"

        # Определяем разделы ДО чистки текста
        sections = detect_sections(raw)
        has_sections = len(sections) > 1
        if has_sections:
            names = [s[0] for s in sections if s[0]]
            self._log(f"Найдено {len(sections)} разделов: {', '.join(names[:5])}{'...' if len(names) > 5 else ''}")
        report(phase="sectioning", progress=20, message="Выделяю разделы и подготавливаю структуру", current_file=filename)

        sections = clean_sections(sections)

        splitter = get_splitter()
        if self._col.count() > 0:
            existing = self._col.get(
                where={"$and": [{"workspace_id": workspace_id}, {"document_id": effective_document_id}]},
                include=[],
            )
            existing_ids = set(existing.get("ids", []) or [])
        else:
            existing_ids = set()
        new_chunks, new_ids, new_metas, seen = [], [], [], set()

        for section_name, section_text in sections:
            if not section_text.strip():
                continue
            chunks = splitter.split_text(section_text)
            for chunk in chunks:
                # Добавляем название раздела в начало чанка
                chunk_with_ctx = f"[{section_name}]\n{chunk}" if section_name else chunk
                h = self._chunk_id(workspace_id, effective_document_id, chunk_with_ctx)
                if h not in existing_ids and h not in seen:
                    seen.add(h)
                    new_chunks.append(chunk_with_ctx)
                    new_ids.append(h)
                    new_metas.append({
                        "workspace_id": workspace_id,
                        "document_id": effective_document_id,
                        "source_file": effective_source_name,
                        "source": file_path,
                        "section": section_name or "",
                        "chunk_id": len(new_chunks) - 1,
                    })

        if not new_chunks:
            report(phase="done", progress=100, message=f"{filename} уже есть в базе", current_file=filename)
            return f"⏭️ {filename} - уже в базе"

        report(phase="chunking", progress=35, message=f"Подготовлено {len(new_chunks)} фрагментов", current_file=filename)
        # Добавляем в ChromaDB пачками по 32
        batch_size = getattr(config, "INDEX_BATCH_SIZE", 64)
        for i in range(0, len(new_chunks), batch_size):
            # Cooperative cancellation checkpoint (Stage 9a): between batches we
            # can abort cleanly. Anything already written this run is rolled
            # back by the caller (document_service.create_document). Note this
            # cannot interrupt model loading or a single embed call.
            if cancel_check is not None and cancel_check():
                raise IndexingCancelled(effective_document_id)
            batch = new_chunks[i:i+batch_size]
            b_ids = new_ids[i:i+batch_size]
            b_metas = new_metas[i:i+batch_size]
            embeddings = self._embeddings.embed_documents(batch)
            self._col.add(ids=b_ids, embeddings=embeddings, documents=batch, metadatas=b_metas)
            pct = min(100, int((i + len(batch)) / len(new_chunks) * 100))
            self._log(f"  {filename}: {pct}%")
            progress_pct = 40 + int(pct * 0.55)
            report(
                phase="indexing",
                progress=min(progress_pct, 95),
                message=f"Сохраняю фрагменты в индекс: {pct}%",
                current_file=filename,
            )

        section_info = f" ({len(sections)} разделов)" if has_sections else ""
        report(phase="done", progress=100, message=f"{filename} готов к поиску", current_file=filename)
        return f"✅ {filename}: добавлено {len(new_chunks)} фрагментов{section_info}"

    def index_all_books(self, *, workspace_id, progress_callback=None):
        """Проиндексировать все файлы из docs/<workspace_id>/"""
        files = storage.iter_workspace_library_files(workspace_id)
        if not files:
            return f"Нет файлов в docs/\nПоддерживаемые форматы: {', '.join(config.SUPPORTED_FORMATS)}"

        def report(**payload):
            if progress_callback:
                progress_callback(**payload)

        report(phase="reading", progress=3, message=f"Найдено файлов: {len(files)}")
        results = [f"📚 Найдено файлов: {len(files)}"]
        for index, fp in enumerate(files, start=1):
            filename = os.path.basename(fp)

            def nested_progress(**payload):
                file_progress = int(payload.get("progress", 0) or 0)
                overall = int(((index - 1) + file_progress / 100) / len(files) * 100)
                report(
                    phase=payload.get("phase", ""),
                    progress=min(max(overall, 3), 99),
                    message=payload.get("message", ""),
                    current_file=payload.get("current_file", filename),
                )

            results.append(self.add_book(fp, workspace_id=workspace_id, progress_callback=nested_progress))
        gc.collect()
        results.append(f"\n📊 Итого в базе: {self._col.count()} фрагментов")
        report(phase="done", progress=100, message="Библиотека полностью переиндексирована")
        return "\n".join(results)

    def clear(self, *, workspace_id):
        """Удалить все чанки указанного workspace из коллекции.

        Раньше эта операция удаляла и пересоздавала всю коллекцию ChromaDB —
        в multi-tenant коллекции это снесло бы данные всех остальных
        workspace. Теперь удаляются только чанки с заданным ``workspace_id``.
        """
        if self._col.count() > 0:
            existing = self._col.get(where={"workspace_id": workspace_id}, include=[])
            ids = existing.get("ids", []) or []
            if ids:
                self._col.delete(ids=ids)

        gc.collect()
        return "✅ База очищена"

    def remove_chunks(self, workspace_id, document_id):
        """Удалить все чанки конкретного документа из коллекции (Stage 3c).

        Точечнее, чем :meth:`remove_book`: ищет по ``document_id`` метаданных,
        а не по ``source_file``. Используется ``document_service`` при
        delete/reindex/replace — наша основная точка входа для аутентифи-
        цированного потока.
        """
        if not document_id:
            return "document_id не указан"

        if self._col.count() == 0:
            return f"⏭️ document_id={document_id} - база уже пуста"

        existing = self._col.get(
            where={"$and": [{"workspace_id": workspace_id}, {"document_id": document_id}]},
            include=[],
        )

        ids = existing.get("ids", []) or []
        if not ids:
            return f"⏭️ document_id={document_id} - в индексе не найден"

        self._col.delete(ids=ids)
        gc.collect()
        return f"🗑️ document_id={document_id}: удалено {len(ids)} фрагментов"

    # ------------------------------------------------------------------
    # Reconcile helpers (Stage 9c): the Document SQL table is the source of
    # truth; these let ``src.maintenance`` find and scrub chunks that no
    # longer have a backing Document row.
    # ------------------------------------------------------------------

    def list_workspace_ids(self):
        """Все ``workspace_id``, присутствующие в индексе (по метаданным чанков).

        Реконсилер перечисляет workspace отсюда, а не из SQL: workspace, у
        которого строки ``Document`` уже стёрты (например, сброс dev-БД),
        иначе бы потерялся, а его осиротевшие чанки остались бы в Chroma.
        """
        if self._col.count() == 0:
            return []
        data = self._col.get(include=["metadatas"])
        workspaces = set()
        for m in data.get("metadatas", []) or []:
            if m:
                ws = m.get("workspace_id")
                if ws:
                    workspaces.add(ws)
        return sorted(workspaces)

    def list_document_ids(self, *, workspace_id):
        """Все ``document_id``, присутствующие в индексе для данного workspace."""
        if self._col.count() == 0:
            return []
        data = self._col.get(where={"workspace_id": workspace_id}, include=["metadatas"])
        doc_ids = set()
        for m in data.get("metadatas", []) or []:
            if m:
                doc_ids.add(m.get("document_id", "") or "")
        return sorted(doc_ids)

    def remove_orphan_chunks(self, *, workspace_id, valid_document_ids):
        """Удалить чанки workspace, чей ``document_id`` не входит в valid-множество.

        ``valid_document_ids`` — это живые ``Document.id`` из SQL для данного
        workspace. Любой чанк с ``document_id`` вне этого множества (включая
        пустой/legacy ``document_id``) считается осиротевшим и удаляется.

        Удаление строго в рамках workspace: выбираются только чанки этого
        ``workspace_id`` и удаляются по их собственным ids — пересечь границу
        tenant'а невозможно. Идемпотентно: повторный вызов не находит сирот и
        ничего не удаляет.

        Возвращает ``{"removed_chunks": int, "removed_document_ids": [...]}``.
        """
        if self._col.count() == 0:
            return {"removed_chunks": 0, "removed_document_ids": []}

        valid = set(valid_document_ids or [])
        data = self._col.get(where={"workspace_id": workspace_id}, include=["metadatas"])
        ids = data.get("ids", []) or []
        metas = data.get("metadatas", []) or []

        orphan_ids = []
        orphan_doc_ids = set()
        for chunk_id, meta in zip(ids, metas):
            doc_id = (meta or {}).get("document_id", "") or ""
            if doc_id not in valid:
                orphan_ids.append(chunk_id)
                orphan_doc_ids.add(doc_id)

        if orphan_ids:
            self._col.delete(ids=orphan_ids)
            gc.collect()
            self._log(
                f"reconcile workspace={workspace_id}: removed {len(orphan_ids)} "
                f"orphan chunks ({len(orphan_doc_ids)} document(s))"
            )

        return {
            "removed_chunks": len(orphan_ids),
            "removed_document_ids": sorted(orphan_doc_ids),
        }

    def remove_book(self, file_name, *, workspace_id):
        """Удалить все чанки файла по ``source_file`` метаданным (legacy).

        Используется Gradio-потоком, где нет ``document_id``. Аутентифицированный
        API-flow Stage 3c использует :meth:`remove_chunks`.
        """
        target_name = os.path.basename(str(file_name or "")).strip()
        if not target_name:
            return "Файл не указан"

        if self._col.count() == 0:
            return f"⏭️ {target_name} - база уже пуста"

        existing = self._col.get(
            where={"$and": [{"workspace_id": workspace_id}, {"source_file": target_name}]},
            include=["metadatas"],
        )

        ids = existing.get("ids", []) or []
        if not ids:
            return f"⏭️ {target_name} - в индексе не найден"

        self._col.delete(ids=ids)
        gc.collect()
        return f"🗑️ {target_name}: удалено {len(ids)} фрагментов"

    def stats(self, *, workspace_id):
        """Статистика: количество файлов, чанков, разделов в рамках workspace."""
        if self._col.count() == 0:
            return {"total_chunks": 0, "total_books": 0, "books": [], "sections": []}
        data = self._col.get(where={"workspace_id": workspace_id}, include=["metadatas"])
        metadatas = data.get("metadatas") or []
        if not metadatas:
            return {"total_chunks": 0, "total_books": 0, "books": [], "sections": []}
        books, sections = set(), set()
        for m in metadatas:
            if m:
                books.add(m.get("source_file", "?"))
                cleaned = self._clean_user_section(m.get("section", ""))
                if cleaned:
                    sections.add(cleaned)
        return {"total_chunks": len(metadatas), "total_books": len(books),
                "books": sorted(books), "sections": sorted(sections, key=self._section_sort_key)}

    @staticmethod
    def _clean_user_section(section):
        section = str(section or "").strip()
        if not section:
            return ""

        return section if is_user_visible_section(section) else ""

    # HyDE: расширение запроса
    def _expand_query(self, query):
        """Генерируем 3 переформулировки вопроса через LLM."""
        if not config.USE_HYDE:
            return [query]
        try:
            prompt = config.PROMPTS["hyde"].format(n=config.HYDE_VARIANTS, query=query)
            result = self._get_llm().call(prompt, temperature=0.4, max_tokens=150)
            variants = [l.strip() for l in result.split("\n") if l.strip()]
            return [query] + variants[:config.HYDE_VARIANTS]
        except Exception:
            return [query]

    # Поиск в ChromaDB
    def _build_where_filter(self, *, workspace_id, file_filter="all", section_filter=None):
        """Строим фильтр для ChromaDB.

        ``workspace_id`` всегда добавляется в фильтр — это единственное
        место, где формируется ``where`` для запросов к коллекции, поэтому
        ни один запрос не может случайно вернуть чанки другого workspace.
        """
        conditions = [{"workspace_id": workspace_id}]
        if file_filter and file_filter != "all":
            conditions.append({"source_file": file_filter})
        if section_filter:
            conditions.append({"section": section_filter})
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}



    def _raw_search(self, queries, kw_filter=None):
        """Для каждого варианта запроса ищем top-20 в ChromaDB"""
        seen, results = set(), []
        n_total = self._col.count()
        if n_total == 0:
            return []
        for q in queries:
            q_embed = self._embeddings.embed_query(q)
            kwargs = dict(
                query_embeddings=[q_embed],
                n_results=min(config.RETRIEVAL_TOP_K, n_total),
                include=["documents", "metadatas", "distances"]
            )
            if kw_filter:
                kwargs["where"] = kw_filter
            try:
                r = self._col.query(**kwargs)
            except Exception:
                continue
            for doc, meta, dist in zip(r["documents"][0], r["metadatas"][0], r["distances"][0]):
                h = self._md5(doc)
                relevance = max(0.0, 1.0 - dist)  # расстояние → сходство
                if h not in seen and relevance >= config.MIN_RELEVANCE:
                    seen.add(h)
                    results.append((doc, meta, relevance))
        return results

    # Переранжирование найденных кандидатов
    def _rerank_candidates(self, query, candidates):
        """Cross-encoder пересчитывает сходство, оставляет top-7"""
        self._ensure_reranker()
        docs = [c[0] for c in candidates]
        if self._reranker and len(docs) > 1:
            pairs = [[query, d] for d in docs]
            scores = self._reranker.predict(pairs)
            ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
            return [c for c, _ in ranked[:config.RERANK_TOP_K]]
        # Если реранкер не загружен - фильтруем по ключевым словам
        words = set(re.findall(r"[А-Яа-яёЁA-Za-z]{3,}", query.lower()))
        def kw(text):
            t = text.lower()
            return sum(1 for w in words if w in t) / max(len(words), 1)
        return sorted(candidates, key=lambda c: kw(c[0]), reverse=True)[:config.RERANK_TOP_K]

    # Сборка контекста для LLM
    def _build_context(self, candidates):
        """Склеиваем фрагменты в текст для отправки в LLM"""
        parts, total = [], 0
        for i, (doc, meta, score) in enumerate(candidates):
            fname = meta.get("source_file", "?")
            section = meta.get("section", "")
            label = f"{fname} | {section}" if section else fname
            block = f"[Фрагмент {i+1} | {label} | score: {score:.2f}]\n{doc.strip()}"
            if total + len(block) > config.MAX_CTX_CHARS:
                left = config.MAX_CTX_CHARS - total
                if left < 200:
                    break
                cut = block[:left].rfind(". ")
                block = block[:cut+1] if cut > 50 else block[:left]
            parts.append(block)
            total += len(block)
        return "\n\n---\n\n".join(parts)

    def get_sections_for_file(self, file_name, *, workspace_id):
        """Получить список разделов конкретного файла."""
        if self._col.count() == 0:
            return []

        data = self._col.get(
            where={"$and": [{"workspace_id": workspace_id}, {"source_file": file_name}]},
            include=["metadatas"]
        )

        sections = set()

        for meta in data.get("metadatas", []):
            section = self._clean_user_section(meta.get("section", ""))

            if section:
                sections.add(section)

        return sorted(sections, key=self._section_sort_key)

    def get_file_profile(self, file_name, *, workspace_id):
        """Краткий профиль материала для продуктовой логики UI."""
        if self._col.count() == 0:
            return {
                "chunk_count": 0,
                "sections_count": 0,
                "sections": [],
            }

        data = self._col.get(
            where={"$and": [{"workspace_id": workspace_id}, {"source_file": file_name}]},
            include=["metadatas"],
        )

        sections = set()
        chunk_count = 0

        for meta in data.get("metadatas", []):
            if not meta:
                continue

            chunk_count += 1
            section = self._clean_user_section(meta.get("section", ""))
            if section:
                sections.add(section)

        ordered_sections = sorted(sections, key=self._section_sort_key)

        return {
            "chunk_count": chunk_count,
            "sections_count": len(ordered_sections),
            "sections": ordered_sections,
        }

    # Распознавание раздела в запросе пользователя
    def get_available_sections(self, *, workspace_id):
        """Список всех разделов в рамках workspace"""
        if self._col.count() == 0:
            return []
        data = self._col.get(where={"workspace_id": workspace_id}, include=["metadatas"])
        return sorted(
            {
                cleaned
                for m in data["metadatas"]
                if m
                for cleaned in [self._clean_user_section(m.get("section", ""))]
                if cleaned
            },
            key=self._section_sort_key,
        )

    def find_section_in_query(self, query, *, workspace_id):
        """
        Ищет в запросе название раздела (с учётом падежей русского языка).
        Например: "из Речи Федра", находит раздел "Речь Федра: ..."
        """
        sections = self.get_available_sections(workspace_id=workspace_id)
        if not sections:
            return None
        query_lower = query.lower()

        # 1 Точное вхождение названия раздела в запрос
        best, best_len = None, 0
        for section in sections:
            if section.lower() in query_lower and len(section) > best_len:
                best, best_len = section, len(section)
                continue
            key_part = section.split(":")[0].strip().lower()
            if len(key_part) >= 5 and key_part in query_lower and len(key_part) > best_len:
                best, best_len = section, len(key_part)
        if best:
            return best

        # 2. Умный поиск через PyMorphy3 (игнорируем падежи)
        try:
            import pymorphy3
            morph = pymorphy3.MorphAnalyzer()

            # Нормализуем слова в запросе (приводим к именительному падежу)
            query_words = [morph.parse(w)[0].normal_form for w in re.findall(r"[а-яё]+", query_lower)]

            for section in sections:
                # Нормализуем слова в названии раздела
                sec_words = [morph.parse(w)[0].normal_form for w in re.findall(r"[а-яё]+", section.lower())]
                # Выделяем ядро названия (слова длиннее 3 букв)
                sec_core = [w for w in sec_words if len(w) > 3]

                # Если хотя бы первые 2 значимых слова из названия раздела есть в запросе — это он
                if sec_core and len(sec_core) >= 2:
                    if sec_core[0] in query_words and sec_core[1] in query_words:
                        return section
        except ImportError:
            pass  # Если библиотека не установлена, возвращаем None (фильтр не применится)

        return None

    def search_with_sources(self, query, file_filter="all", section_filter=None, *, workspace_id):
        """
        Возвращает контекст для LLM и список источников,
        найденных RAG-пайплайном.
        """
        if self._col.count() == 0:
            return "", []

        kw_filter = self._build_where_filter(workspace_id=workspace_id, file_filter=file_filter, section_filter=section_filter)
        queries = self._expand_query(query)
        cands = self._raw_search(queries, kw_filter)

        if not cands:
            if file_filter != "all" or section_filter:
                return "", []

            q_e = self._embeddings.embed_query(query)
            fallback = dict(
                query_embeddings=[q_e],
                n_results=min(5, self._col.count()),
                include=["documents", "metadatas", "distances"],
                where={"workspace_id": workspace_id},
            )
            r = self._col.query(**fallback)
            cands = [
                (d, m, max(0.0, 1.0 - dist))
                for d, m, dist in zip(
                    r["documents"][0],
                    r["metadatas"][0],
                    r["distances"][0]
                )
            ]

        if not cands:
            return "", []

        ranked = self._rerank_candidates(query, cands)
        context = self._build_context(ranked)

        sources = []
        seen = set()

        for doc, meta, score in ranked:
            source_file = meta.get("source_file", "?")
            section = meta.get("section", "")
            key = (source_file, section, doc[:80])

            if key in seen:
                continue

            seen.add(key)

            sources.append({
                "source_file": source_file,
                "section": section,
                "score": round(float(score), 3),
                "text": doc.strip(),
            })

        return context, sources

    def _is_noise_summary_chunk(self, text):
        """Отсекает мусорные чанки для конспекта: оглавление, ISBN, списки иллюстраций."""
        if not text:
            return True

        t = text.lower()
        text_without_label = re.sub(r"^\s*\[[^\]]+\]\s*", "", text.strip())

        noise_markers = [
            "оглавление",
            "содержание",
            "isbn",
            "список иллюстраций",
            "список литературы",
            "библиографический список",
            "учебник предназначен",
            "министерство науки",
            "издательство",
            "автор фото",
            "риа новости",
            "цит. по",
            "цит по",
            "список источников",
            "источники иллюстраций",
            "описание изображения",
            "ссылка на архив",
        ]

        if any(marker in t for marker in noise_markers):
            return True

        # Много точек подряд часто означает оглавление
        if text.count(".....") >= 2:
            return True

        if re.search(
            r"^\s*\d{1,3}\.\s+.{0,160}(плакат|портрет|фото|цит\.?\s+по|история россии)",
            text_without_label.lower(),
            flags=re.DOTALL,
        ):
            return True

        numbered_caption_lines = re.findall(
            r"(?m)^\s*\d{1,3}\.\s+.{0,180}(плакат|портрет|фото|цит\.?\s+по|автор фото)",
            text_without_label.lower(),
        )
        if len(numbered_caption_lines) >= 1:
            return True

        numbered_lines = re.findall(r"(?m)^\s*\d{1,3}\.\s+\S+", text_without_label)
        if len(numbered_lines) >= 3:
            return True

        source_density_markers = [
            "цит.",
            "автор фото",
            "©",
            "риа новости",
            "архив",
            "история россии: в 20 т.",
        ]
        if sum(1 for marker in source_density_markers if marker in t) >= 2:
            return True

        # Слишком короткий фрагмент бесполезен
        if len(text.strip()) < 250:
            return True

        return False

    @staticmethod
    def _section_sort_key(section):
        """Натуральная сортировка разделов: Глава 2 раньше Главы 12."""
        text = str(section or "").strip().lower()

        chapter = re.match(r"^глава\s+(\d+)\b", text)
        if chapter:
            return (0, int(chapter.group(1)), text)

        paragraph = re.match(r"^§\s*(\d+)\b", text)
        if paragraph:
            return (1, int(paragraph.group(1)), text)

        numbers = re.findall(r"\d+", text)
        if numbers:
            return (2, int(numbers[0]), text)

        return (3, text)

    def _query_year_bounds(self, query):
        """Возвращает нижнюю и верхнюю границу годов из темы, если их можно вывести."""
        q = query.lower()
        years = [int(y) for y in re.findall(r"\b(1[0-9]{3}|20[0-9]{2})\b", q)]

        if len(years) >= 2:
            return min(years), max(years)

        if not years:
            return None, None

        year = years[0]
        start, end = None, None

        if re.search(r"\b(до|перед)\s+" + str(year) + r"\b", q):
            end = year
        if re.search(r"\b(после|с|от)\s+" + str(year) + r"\b", q):
            start = year

        # Частый учебный запрос: после Николая II фактически означает период
        # после крушения монархии и революции 1917 года.
        if end and ("николая ii" in q or "николай ii" in q):
            start = 1917

        return start, end

    @staticmethod
    def _years_from_text(text):
        """Извлекает годы из текста в виде чисел."""
        return [int(y) for y in re.findall(r"\b(1[0-9]{3}|20[0-9]{2})\b", text.lower())]

    def _is_out_of_topic_year_range(self, text, query):
        """
        Отсекает фрагменты, которые по явным годам находятся вне периода темы.

        Смешанные фрагменты тоже отбрасываются, если годов после верхней границы
        больше, чем годов внутри диапазона: это снижает утечки в 2000-е/2010-е.
        """
        start, end = self._query_year_bounds(query)
        if start is None and end is None:
            return False

        years = self._years_from_text(text)
        if not years:
            return False

        inside = [
            year for year in years
            if (start is None or year >= start) and (end is None or year <= end)
        ]
        before = [year for year in years if start is not None and year < start]
        after = [year for year in years if end is not None and year > end]

        if not inside and (before or after):
            return True

        if after and len(after) > len(inside):
            return True

        if before and len(before) > len(inside) and len(before) >= 3:
            return True

        return False

    def _topic_lexical_score(self, text, query):
        """
        Дополнительная оценка для тематического конспекта.
        Нужна, чтобы темы типа 'Россия после Николая II до 2000 года'
        не улетали в древность, Петра I и Александра II.
        """
        t = text.lower()
        q = query.lower()
        normalized_text = re.sub(r"[^а-яёa-z0-9]+", " ", t).strip()

        score = 0

        if self._is_out_of_topic_year_range(t, q):
            return 0

        # Общие слова из запроса
        words = re.findall(r"[а-яёa-z0-9]{3,}", q)
        stop = {
            "что", "это", "как", "где", "когда", "после", "года",
            "год", "лет", "тема", "период", "россия", "россии",
        }

        for word in words:
            if word not in stop and word in t:
                score += 2

        meaningful_words = [word for word in words if word not in stop]
        normalized_query = " ".join(meaningful_words)

        if normalized_query and normalized_query in normalized_text:
            score += 30 + len(meaningful_words) * 3

        if len(meaningful_words) >= 2:
            for left, right in zip(meaningful_words, meaningful_words[1:]):
                if f"{left} {right}" in normalized_text:
                    score += 5

            if all(word in normalized_text for word in meaningful_words):
                score += 10

        start, end = self._query_year_bounds(query)
        chunk_years = self._years_from_text(text)

        if start is not None or end is not None:
            in_range = []
            before_range = []
            after_range = []

            for year in chunk_years:
                if start is not None and year < start:
                    before_range.append(year)
                elif end is not None and year > end:
                    after_range.append(year)
                else:
                    in_range.append(year)

            if chunk_years:
                if not in_range:
                    return -20.0

                score += len(in_range) * 5
                score -= len(before_range) * 3
                score -= len(after_range) * 8

                if after_range and len(after_range) >= len(in_range):
                    score -= 12 * (len(after_range) - len(in_range) + 1)

        # Исторические маркеры для XX века
        history_markers = [
            "николай ii", "1917", "феврал", "октябр", "революц",
            "временное правительство", "большев", "ленин",
            "гражданской вой", "гражданская вой", "нэп",
            "советской россии", "ссср", "сталин",
            "индустриализац", "коллективизац",
            "великая отечественная", "1941", "1945",
            "хрущ", "брежнев", "застой",
            "перестройк", "горбач", "1990", "1991",
            "распад ссср", "ельцин", "россия 1990",
            "экономических реформ", "конституция 1993",
        ]

        for marker in history_markers:
            if marker in t:
                score += 4

        # Штрафы за явно ранние эпохи
        old_markers = [
            "древняя русь", "монгольское нашествие", "золотой орды",
            "иван грозный", "петр i", "екатерина ii",
            "александр i", "николай i", "александр ii",
            "xviii", "xix"
        ]

        for marker in old_markers:
            if marker in t:
                score -= 4

        return score

    def _lexical_candidates_for_summary(self, query, file_filter="all", section_filter=None, limit=120, *, workspace_id):
        """
        Дополнительный лексический поиск по всей базе/файлу.
        Нужен для больших учебников, когда semantic search цепляет оглавление и ранние главы.
        """
        where = self._build_where_filter(workspace_id=workspace_id, file_filter=file_filter, section_filter=section_filter)
        data = self._col.get(
            where=where,
            include=["documents", "metadatas"]
        )

        scored = []

        for doc, meta in zip(data.get("documents", []), data.get("metadatas", [])):
            if self._is_noise_summary_chunk(doc):
                continue

            score = self._topic_lexical_score(doc, query)

            if score > 0:
                scored.append((score, doc, meta))

        scored.sort(key=lambda x: x[0], reverse=True)

        result = []

        for score, doc, meta in scored[:limit]:
            result.append((doc, meta, float(score)))

        return result

    def search_chunks_for_summary(self, query, file_filter="all", section_filter=None, top_k=None, *, workspace_id):
        """
        Поиск чанков для тематического конспекта.

        Комбинирует:
        1. Semantic search через BGE-M3;
        2. Rerank через BGE-Reranker;
        3. Лексический добор по годам и историческим маркерам;
        4. Фильтр мусора: оглавление, ISBN, список иллюстраций.
        """
        if self._col.count() == 0:
            return []

        if top_k is None:
            top_k = config.SUMMARY_TOP_K

        kw_filter = self._build_where_filter(workspace_id=workspace_id, file_filter=file_filter, section_filter=section_filter)

        # 1. Semantic search
        queries = self._expand_query(query)

        original_top_k = config.RETRIEVAL_TOP_K

        try:
            config.RETRIEVAL_TOP_K = max(original_top_k, top_k * 3)
            semantic_candidates = self._raw_search(queries, kw_filter)
        finally:
            config.RETRIEVAL_TOP_K = original_top_k

        # 2. Лексический добор по датам/маркерам
        lexical_candidates = self._lexical_candidates_for_summary(
            query=query,
            file_filter=file_filter,
            section_filter=section_filter,
            limit=top_k * 3,
            workspace_id=workspace_id,
        )

        # 3. Объединяем кандидатов без дублей
        combined = []
        seen = set()

        for doc, meta, score in semantic_candidates + lexical_candidates:
            if self._is_noise_summary_chunk(doc):
                continue

            if self._is_out_of_topic_year_range(doc, query):
                continue

            h = self._md5(doc)

            if h in seen:
                continue

            seen.add(h)
            combined.append((doc, meta, score))

        # 3a. Defensive fallback. If semantic + lexical (after filtering) leave
        # us empty but the workspace actually owns chunks matching kw_filter,
        # surface those chunks directly. Mirrors search_with_sources so the
        # summary path stops telling the user "topic not found" while chat
        # finds the same material — Stage 6 smoke surfaced this for short
        # plain-text uploads where _is_noise_summary_chunk's 250-char cutoff
        # eats the entire file. The noise filter is a big-book quality
        # heuristic, not a workspace-membership check, so it is intentionally
        # not applied here. Year-range filter stays: it is about topic
        # relevance, not chunk quality.
        if not combined:
            try:
                fallback = self._col.get(
                    where=kw_filter,
                    include=["documents", "metadatas"],
                )
            except Exception:
                fallback = {"documents": [], "metadatas": []}

            for doc, meta in zip(
                fallback.get("documents", []) or [],
                fallback.get("metadatas", []) or [],
            ):
                if not doc:
                    continue
                if self._is_out_of_topic_year_range(doc, query):
                    continue
                h = self._md5(doc)
                if h in seen:
                    continue
                seen.add(h)
                combined.append((doc, meta, 0.0))

        if not combined:
            return []

        # 4. Реранк
        self._ensure_reranker()

        if self._reranker and len(combined) > 1:
            docs = [c[0] for c in combined]
            pairs = [[query, d] for d in docs]
            scores = self._reranker.predict(pairs)

            ranked = []

            for candidate, rerank_score in zip(combined, scores):
                doc, meta, _ = candidate
                lexical_bonus = self._topic_lexical_score(doc, query)
                final_score = float(rerank_score) + lexical_bonus * 0.15
                ranked.append((candidate, final_score))

            ranked.sort(key=lambda x: x[1], reverse=True)
            best = ranked[:top_k]
        else:
            ranked = []

            for candidate in combined:
                doc, meta, base_score = candidate
                lexical_bonus = self._topic_lexical_score(doc, query)
                final_score = float(base_score) + lexical_bonus
                ranked.append((candidate, final_score))

            ranked.sort(key=lambda x: x[1], reverse=True)
            best = ranked[:top_k]

        # 5. Возвращаем в порядке документа
        result = []

        for (doc, meta, _), score in best:
            result.append({
                "text": doc,
                "source_file": meta.get("source_file", "?"),
                "section": meta.get("section", ""),
                "chunk_id": meta.get("chunk_id", 0),
                "score": round(float(score), 3),
            })

        result.sort(key=lambda x: (x["source_file"], int(x["chunk_id"])))

        return result

    def search(self, query, file_filter="all", section_filter=None, *, workspace_id):
        """
        Старый интерфейс поиска: возвращает только контекст.
        Оставлен для совместимости.
        """
        context, _ = self.search_with_sources(query, file_filter, section_filter, workspace_id=workspace_id)
        return context

    def get_file_chunks(self, file_filter="all", section_filter=None, *, workspace_id):
        """Получить чанки выбранного файла и, при необходимости, выбранного раздела."""
        if self._col.count() == 0:
            return []

        where = self._build_where_filter(workspace_id=workspace_id, file_filter=file_filter, section_filter=section_filter)
        data = self._col.get(
            where=where,
            include=["documents", "metadatas"]
        )

        chunks = []

        for doc, meta in zip(data.get("documents", []), data.get("metadatas", [])):
            chunks.append({
                "text": doc,
                "source_file": meta.get("source_file", "?"),
                "section": meta.get("section", ""),
                "chunk_id": meta.get("chunk_id", 0),
            })

        chunks.sort(key=lambda x: (x["source_file"], int(x["chunk_id"])))
        return chunks

    def get_available_files(self, *, workspace_id):
        """Список файлов workspace (для выпадающего списка)"""
        if self._col.count() == 0:
            return []
        data = self._col.get(where={"workspace_id": workspace_id}, include=["metadatas"])
        return sorted({m.get("source_file", "") for m in data["metadatas"] if m and m.get("source_file")})
