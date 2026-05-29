"""
run.py - удобная точка входа для запуска BonchMind Pro.
"""

import os
import sys

import config
from main import build_gui


def main():
    config_errors = config.validate_config()
    if config_errors:
        print("Ошибки конфигурации:")
        for err in config_errors:
            print(f" - {err}")
        sys.exit(1)

    for d in [config.DOCS_DIR, config.DATA_DIR]:
        os.makedirs(d, exist_ok=True)

    mode = config.LLM_MODE
    if mode == "api":
        llm_label = f"API / {getattr(config, 'API_MODEL', '?')}"
    else:
        llm_label = f"OLLAMA / {config.OLLAMA_MODEL}"

    print("BonchMind Pro")
    print(f"LLM: {llm_label}")
    print(f"Эмбеддинги: {config.EMBEDDING_MODEL}")
    print(f"Реранкер: {config.RERANKER_MODEL}")
    print(f"Чанк: {config.CHUNK_SIZE} симв.")
    print(f"HyDE: {'вкл' if config.USE_HYDE else 'выкл'}")

    app = build_gui()
    app.launch(
        server_port=config.GUI_PORT,
        share=config.GUI_SHARE,
        inbrowser=True,
    )


if __name__ == "__main__":
    main()