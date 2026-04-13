FROM ghcr.io/astral-sh/uv:python3.14-bookworm

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY shared ./shared
COPY services ./services

ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

CMD ["uvicorn", "services.registry.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
