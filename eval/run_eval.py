"""
run_eval.py - простая проверка качества поиска BonchMind Pro.
Проверяет, попал ли ожидаемый файл/раздел в найденный контекст.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge_base import KnowledgeBase


def load_questions(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize(text: str) -> str:
    return (text or "").lower().strip()


def main():
    questions_path = Path(__file__).parent / "questions.json"
    questions = load_questions(str(questions_path))

    kb = KnowledgeBase()
    total = len(questions)
    file_hits = 0
    section_hits = 0

    print("=" * 60)
    print("BonchMind Pro Evaluation")
    print("=" * 60)

    for i, item in enumerate(questions, start=1):
        question = item["question"]
        expected_file = item.get("expected_file", "")
        expected_section = item.get("expected_section", "")

        section_filter = kb.find_section_in_query(question)
        context = kb.search(
            question,
            file_filter="all",
            section_filter=section_filter,
        )

        context_norm = normalize(context)
        file_ok = normalize(expected_file) in context_norm if expected_file else True
        section_ok = normalize(expected_section) in context_norm if expected_section else True

        if file_ok:
            file_hits += 1
        if section_ok:
            section_hits += 1

        print()
        print(f"[{i}] {question}")
        print(f"  Expected file   : {expected_file or '-'}")
        print(f"  Expected section: {expected_section or '-'}")
        print(f"  File hit        : {'YES' if file_ok else 'NO'}")
        print(f"  Section hit     : {'YES' if section_ok else 'NO'}")

    print()
    print("=" * 60)
    print(f"Total questions : {total}")
    print(f"File recall     : {file_hits}/{total} ({file_hits / total:.0%})")
    print(f"Section recall  : {section_hits}/{total} ({section_hits / total:.0%})")
    print("=" * 60)


if __name__ == "__main__":
    main()