"""Full-file (no-topic) summary cap.

A big material must be truncated to its first N chunks with an honest notice,
so the empty-topic map-reduce can't fan out into dozens of sequential LLM calls
(the timeout/connection-reset fix for "конспект по всему материалу").
"""

import config
from src.summary_engine import generate_full_file_summary

TEST_WORKSPACE_ID = "ws-fullfile-cap"


class ManyChunksKB:
    def __init__(self, n):
        self._n = n

    def get_file_chunks(self, file_filter="all", section_filter=None, workspace_id=None):
        return [
            {"text": f"chunk-{i}", "source_file": "big.pdf", "section": "", "chunk_id": i}
            for i in range(self._n)
        ]


class RecordingLLM:
    def __init__(self):
        self.calls = 0
        self.prompts = []

    def call(self, prompt, max_tokens=None, temperature=None):
        self.calls += 1
        self.prompts.append(prompt)
        return "partial"


def _run(kb, llm):
    return generate_full_file_summary(
        kb=kb,
        llm=llm,
        selected_file="big.pdf",
        selected_section="Все разделы",
        summary_type="Средний",
        file_filter="big.pdf",
        workspace_id=TEST_WORKSPACE_ID,
    )


def test_big_material_is_capped_and_flagged(monkeypatch):
    monkeypatch.setattr(config, "FULL_FILE_SUMMARY_MAX_CHUNKS", 10)
    kb = ManyChunksKB(100)
    llm = RecordingLLM()

    result = _run(kb, llm)

    # Honest truncation notice naming the cap and the real total.
    assert "первым 10 фрагментам из 100" in result
    # Only the first 10 chunks reached the LLM; the tail never did.
    joined = "\n".join(llm.prompts)
    assert "chunk-0" in joined
    assert "chunk-9" in joined
    assert "chunk-10" not in joined
    assert "chunk-99" not in joined


def test_small_material_not_capped_or_flagged(monkeypatch):
    monkeypatch.setattr(config, "FULL_FILE_SUMMARY_MAX_CHUNKS", 60)
    kb = ManyChunksKB(5)
    llm = RecordingLLM()

    result = _run(kb, llm)

    assert "Материал большой" not in result
    joined = "\n".join(llm.prompts)
    assert "chunk-4" in joined
