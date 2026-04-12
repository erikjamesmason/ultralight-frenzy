FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install uv from the official distroless image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy source and install dependencies
# (single COPY keeps the layer simple; add a .dockerignore to keep context small)
COPY . .
RUN uv sync --no-dev

# Install Playwright's Chromium browser + system deps (needed for JS-heavy sites like REI)
RUN uv run playwright install --with-deps chromium

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV CHROMA_PERSIST_PATH=/data/chroma
ENV PATH="/app/.venv/bin:$PATH"

# Pre-create the local data dir (used when running without a Chroma server)
RUN mkdir -p /data/chroma

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
