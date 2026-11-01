# One image for the API and the worker (Railway runs two services from it with different start commands).
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.11.32
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY services/agent/pyproject.toml services/agent/pyproject.toml
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/worker/pyproject.toml services/worker/pyproject.toml
COPY services ./services
RUN uv sync --frozen --no-dev --all-packages
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
ENV PATH="/app/.venv/bin:$PATH" PORT=8000
EXPOSE 8000
# default: API. The worker service overrides the start command with `rahbar-worker`.
CMD ["sh", "-c", "uvicorn rahbar_api.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
