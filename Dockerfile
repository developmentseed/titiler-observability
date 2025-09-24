FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  apt-get update && apt-get install -y git && \ 
  uv sync --locked --no-install-project

COPY pyproject.toml uv.lock main.py /app/.

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --locked

CMD ["uv", "run", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:8000", "--workers", "1"]
