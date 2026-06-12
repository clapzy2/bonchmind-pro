# Backend image for BonchMind Pro (FastAPI + ChromaDB + BGE models).
#
# Notes:
# - CPU-only torch is installed first, from the PyTorch CPU index, so
#   sentence-transformers does not pull the multi-GB CUDA build. The app runs
#   embeddings/rerank on CPU (EMBEDDING_DEVICE=cpu).
# - Embedding/reranker weights are NOT baked in; they download on first use to
#   HF_HOME, which docker-compose mounts as a named volume so the ~2 GB
#   download only happens once.
# - The entrypoint runs ``alembic upgrade head`` before starting the API, so a
#   fresh Postgres volume is migrated automatically.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    HF_HOME=/models

WORKDIR /app

# CPU-only torch first (keeps the image lean; the default PyPI torch bundles CUDA).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker/entrypoint.sh"]
