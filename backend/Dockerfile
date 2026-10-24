FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the RAG embedding model into the image, so the first question needs no download.
ENV RAG_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5 \
    RAG_MODEL_CACHE_DIR=/app/models
RUN python -c "import os; from fastembed import TextEmbedding; \
TextEmbedding(os.environ['RAG_EMBEDDING_MODEL'], cache_dir=os.environ['RAG_MODEL_CACHE_DIR'])" \
    && chmod -R a+rwX /app/models

COPY app ./app

# Run as an unprivileged user, so a compromise of the app doesn't hand over root.
RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8000
# Honour the platform-provided $PORT (Render/Fly/Railway) and default to 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
