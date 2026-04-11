FROM python:3.12-slim

WORKDIR /app

# Install uv from the official distroless image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy source and install dependencies
# (single COPY keeps the layer simple; add a .dockerignore to keep context small)
COPY . .
RUN uv sync --no-dev

ENV PYTHONUNBUFFERED=1
ENV CHROMA_PERSIST_PATH=/data/chroma

# Pre-create the local data dir (used when running without a Chroma server)
RUN mkdir -p /data/chroma

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
