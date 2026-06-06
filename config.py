"""
config.py - все настройки системы в одном месте.
Меняя этот файл, можно переключать режимы работы без изменения кода.
"""
import os
from dotenv import load_dotenv
from src.prompts import SYSTEM_PROMPT, PROMPTS

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Папки проекта
DOCS_DIR   = os.path.join(BASE_DIR, "docs")
DATA_DIR   = os.path.join(BASE_DIR, "data")
CHROMA_DIR = os.path.join(DATA_DIR, "chromadb")

# Режим работы LLM: "api" (облако) или "ollama" (локально)
LLM_MODE = os.getenv("LLM_MODE", "api")

# Настройки API (OpenRouter)
API_URL   = "https://openrouter.ai/api/v1/chat/completions"
API_KEY  = os.getenv("API_KEY", "")
API_MODEL = os.getenv("API_MODEL", "qwen/qwen3-32b")

# Настройки Ollama (локальный режим)
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")

# Параметры генерации
LLM_MAX_TOKENS     = 2048
LLM_TEMPERATURE    = 0.1
LLM_TOP_P         = 0.9
LLM_REPEAT_PENALTY = 1.15
LLM_CONTEXT_SIZE   = 32768

# Эмбеддинги
EMBEDDING_MODEL  = "BAAI/bge-m3"
EMBEDDING_DEVICE = "cpu"

# Реранкер
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
USE_RERANKER   = True

# ChromaDB
COLLECTION_NAME = "textbot_docs"

# Чанкинг
CHUNK_SIZE    = 1200
CHUNK_OVERLAP = 200

# Индексация
INDEX_BATCH_SIZE = 64

# Поиск
RETRIEVAL_TOP_K = 80
MIN_RELEVANCE   = 0.00
MAX_CTX_CHARS   = 18000
RERANK_TOP_K    = 12
SUMMARY_TOP_K   = 40

# Плановый тематический конспект
PLANNED_SUMMARY_ENABLED = True
PLANNED_SUMMARY_QUERIES = 7
PLANNED_SUMMARY_CHUNKS_PER_QUERY = 5
PLANNED_SUMMARY_MAX_CHUNKS = 40
PLANNED_SUMMARY_MAX_CHUNKS_PER_SECTION = 4

# HyDE
USE_HYDE      = False
HYDE_VARIANTS = 3

# Форматы файлов
SUPPORTED_FORMATS = [
    ".pdf", ".txt", ".epub", ".docx",
    ".md", ".fb2", ".fb2.zip", ".html", ".htm", # добавить еще
]

# Веб-интерфейс
GUI_PORT  = 7860
GUI_SHARE = False

def validate_config():
    """Проверяет базовые настройки проекта."""
    errors = []

    if LLM_MODE not in ["api", "ollama"]:
        errors.append("LLM_MODE должен быть 'api' или 'ollama'.")

    if LLM_MODE == "api" and not API_KEY:
        errors.append("Для режима api необходимо указать API_KEY в .env.")

    if CHUNK_OVERLAP >= CHUNK_SIZE:
        errors.append("CHUNK_OVERLAP должен быть меньше CHUNK_SIZE.")

    if RETRIEVAL_TOP_K < RERANK_TOP_K:
        errors.append("RETRIEVAL_TOP_K должен быть больше или равен RERANK_TOP_K.")

    return errors