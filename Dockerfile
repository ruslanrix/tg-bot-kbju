FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Poetry
RUN pip install "poetry>=2.2,<3.0"

# Copy dependency files first for caching
COPY pyproject.toml poetry.lock ./

# Install production deps only (no dev, no root package)
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --only main

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Default port (Railway sets PORT env)
ENV PORT=8000

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn app.web.main:app --host 0.0.0.0 --port ${PORT}"]
