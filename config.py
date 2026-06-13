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
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")

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

# Полнофайловый конспект (без темы): потолок фрагментов для map-reduce. На
# большом материале полный обход = десятки последовательных вызовов LLM
# (зависание / обрыв соединения). Сверх потолка берём первые N фрагментов и
# честно помечаем конспект как «по началу материала». 0 = без потолка.
FULL_FILE_SUMMARY_MAX_CHUNKS = 60

# HyDE
USE_HYDE      = False
HYDE_VARIANTS = 3

# Форматы файлов
SUPPORTED_FORMATS = [
    ".pdf", ".txt", ".epub", ".docx",
    ".md", ".fb2", ".fb2.zip", ".html", ".htm", # добавить еще
]

# Лимит загрузки (байт). По умолчанию 50 МБ.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Веб-интерфейс
GUI_PORT  = 7860
GUI_SHARE = False

# --- Multi-user foundation (Stage 1: db + auth) ---------------------------
#
# Database URL is read from env so dev/CI can stay on SQLite while production
# moves to Postgres without code changes. Tests provide their own URL via the
# DATABASE_URL env var (see tests/conftest.py).
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(DATA_DIR, 'app.db')}")

# JWT secret. Production MUST set JWT_SECRET_KEY in the environment; the dev
# fallback below is only acceptable for local development and tests. The
# fallback is intentionally obviously-non-secret so accidentally shipping it to
# production is easy to notice in a security scan.
JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "dev-only-insecure-jwt-secret-change-me-in-production",
)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
# Access-token lifetime. Default: 7 days (60 * 24 * 7).
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 7)))

# Cookie carrying the access token. HttpOnly + SameSite=Lax by default.
AUTH_COOKIE_NAME = "bonchmind_auth"
# Set to True only when serving the frontend over HTTPS in production.
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"

# Protected "root" admin (Stage 13). The user whose email matches this can
# never be demoted or banned through the admin API — not even by another
# superuser. Set it to your own login email. Empty (default) = no protected
# root. It does not auto-grant superuser; promote the account once as usual.
ROOT_ADMIN_EMAIL = os.getenv("ROOT_ADMIN_EMAIL", "").strip().lower()

# --- Rate limiting (Stage 9a) ---------------------------------------------
# Per-IP limits applied via slowapi. Tunable through env; strict on auth,
# moderate on chat/upload. Disable entirely with RATE_LIMIT_ENABLED=false
# (used by the test suite).
RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "10/minute")
RATE_LIMIT_REGISTER = os.getenv("RATE_LIMIT_REGISTER", "5/minute")
RATE_LIMIT_CHAT = os.getenv("RATE_LIMIT_CHAT", "30/minute")
RATE_LIMIT_UPLOAD = os.getenv("RATE_LIMIT_UPLOAD", "20/minute")


# --- Plans & quotas (Stage 12) --------------------------------------------
# Per-plan usage limits, enforced via ``src.quota``. All numbers are
# env-overridable so they can be tuned without a migration. Disable enforcement
# entirely with QUOTAS_ENABLED=false (the test suite does this; quota-specific
# tests flip it back on for their scope).
#
# ``max_materials`` is a *total* cap (current Document count); ``chat_per_day``
# / ``summary_per_day`` are rolling per-UTC-day caps. ``model`` is a forward
# hook for a cheaper free-tier model — both plans point at the configured model
# for now.
QUOTAS_ENABLED = os.getenv("QUOTAS_ENABLED", "true").lower() in ("1", "true", "yes", "on")

_DEFAULT_MODEL = API_MODEL if LLM_MODE == "api" else OLLAMA_MODEL


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


PLAN_LIMITS = {
    "free": {
        "max_materials": _int_env("PLAN_FREE_MAX_MATERIALS", 3),
        "chat_per_day": _int_env("PLAN_FREE_CHAT_PER_DAY", 15),
        "summary_per_day": _int_env("PLAN_FREE_SUMMARY_PER_DAY", 3),
        "model": os.getenv("PLAN_FREE_MODEL", _DEFAULT_MODEL),
    },
    "pro": {
        "max_materials": _int_env("PLAN_PRO_MAX_MATERIALS", 50),
        "chat_per_day": _int_env("PLAN_PRO_CHAT_PER_DAY", 200),
        "summary_per_day": _int_env("PLAN_PRO_SUMMARY_PER_DAY", 50),
        "model": os.getenv("PLAN_PRO_MODEL", _DEFAULT_MODEL),
    },
}


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