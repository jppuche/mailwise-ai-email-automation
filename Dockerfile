# Stage 1: builder — install Python dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

COPY pyproject.toml .
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Stage 2: runtime — lean production image
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN groupadd -r app && useradd -r -g app app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/src ./src
COPY --from=builder /app/pyproject.toml .
COPY --from=builder /app/mailwise.egg-info ./mailwise.egg-info
COPY docker/ ./docker/
COPY alembic/ ./alembic/
COPY alembic.ini .
RUN sed -i 's/\r$//' ./docker/healthchecks/*.sh && chmod +x ./docker/healthchecks/*.sh

USER app

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
