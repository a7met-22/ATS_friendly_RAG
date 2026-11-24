FROM python:3.12-slim

ARG APP_UID=1000
ARG APP_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/appuser

WORKDIR /app

# Create a non-root application user for security hardening.
RUN groupadd --gid ${APP_GID} appuser \
    && useradd \
        --uid ${APP_UID} \
        --gid appuser \
        --create-home \
        appuser

# Install Python dependencies first for optimal Docker layer caching.
COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt\
    && python -m spacy download en_core_web_lg

# Copy application source code with proper ownership directly.
COPY --chown=appuser:appuser . .

# Prepare writable runtime directories.
RUN mkdir -p /app/uploaded_pdfs /app/local_models \
    && chown -R appuser:appuser /app /home/appuser

USER appuser

EXPOSE 8000

# Built-in container healthcheck hitting FastAPI readiness probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0', timeout=3)" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
