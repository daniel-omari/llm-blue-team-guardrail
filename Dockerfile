# Single-container build: the React UI and the FastAPI API in one image, for a
# one-service deploy (e.g. Hugging Face Spaces). For local development use the
# separate services in docker-compose.yml instead.

# --- Stage 1: build the React frontend (same-origin API base) ---
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# The API is served by this same container, so the UI calls same-origin paths
# (/classify, /history). Inject an empty API base for this build only.
RUN echo "VITE_API_BASE=" > .env.production.local && npm run build

# --- Stage 2: Python runtime serving the API + the built UI ---
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Bake the RAG embedding model into the image, so the first question needs no
# download. The Space runs as a non-root user, so the cache must be writable by it.
ENV RAG_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5 \
    RAG_MODEL_CACHE_DIR=/app/models
RUN python -c "import os; from fastembed import TextEmbedding; \
TextEmbedding(os.environ['RAG_EMBEDDING_MODEL'], cache_dir=os.environ['RAG_MODEL_CACHE_DIR'])" \
    && chmod -R a+rwX /app/models

COPY backend/app ./app
# Drop the built frontend where FastAPI's StaticFiles mount looks for it.
COPY --from=frontend /frontend/dist ./app/static

# Hugging Face Spaces serves on 7860; SQLite lives in writable /tmp. The MCP
# endpoint (/mcp) only answers to these host names (DNS-rebinding protection).
ENV PORT=7860
ENV DATABASE_URL=sqlite:////tmp/guardrail.db
ENV MCP_ALLOWED_HOSTS="localhost:*,127.0.0.1:*,daniel-omari-llm-blue-team-guardrail.hf.space"
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
