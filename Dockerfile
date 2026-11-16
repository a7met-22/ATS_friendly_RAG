

FROM python:3.12-slim

ARG APP_UID=1000
ARG APP_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/appuser

WORKDIR /app

# Create a non-root application user.
RUN groupadd --gid ${APP_GID} appuser \
    && useradd \
        --uid ${APP_UID} \
        --gid appuser \
        --create-home \
        appuser

# Install Python dependencies first for better layer caching.
COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Copy application source code.
COPY . .

# Prepare writable application directories.
RUN mkdir -p /app/uploaded_pdfs /home/appuser/.streamlit \
    && chown -R appuser:appuser /app /home/appuser

USER appuser

EXPOSE 8501

CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true"]