"""Centralized configuration management for the RAG project."""

import os
from pathlib import Path

from dotenv import load_dotenv


# Resolve the project root from this file's location.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Define shared project paths.
ENV_FILE = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "uploaded_pdfs"

# Load environment variables once from the project's .env file.
load_dotenv(ENV_FILE)


def get_required_env(name: str) -> str:
    """Return a required environment variable or raise a clear error."""
    value = os.getenv(name)

    if not value or not value.strip():
        raise ValueError(
            f"Required environment variable '{name}' is missing or empty. "
            f"Check the configuration file: {ENV_FILE}"
        )

    return value


# Parsing configuration ("llama" or "pymupdf")
PARSER_TYPE = os.getenv("PARSER_TYPE", "pymupdf").strip().lower()

# Generation & Embedding Models
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")

# External service configuration
LLAMA_CLOUD_API_KEY = get_required_env("LLAMA_CLOUD_API_KEY")
GEMINI_API_KEY = get_required_env("GEMINI_API_KEY")

# Database configuration
DB_HOST = get_required_env("DB_HOST")
DB_PORT = int(get_required_env("DB_PORT"))
DB_NAME = get_required_env("DB_NAME")
DB_USER = get_required_env("DB_USER")
DB_PASSWORD = get_required_env("DB_PASSWORD")

# Database Connection Pool configuration
DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "5"))
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "50"))


# FastAPI Security, JWT & CORS configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION_SUPER_SECRET_KEY")
JWT_ALGORITHM = "HS256"

# Comma-separated list of allowed frontend domains (e.g., "http://localhost:3000,https://example.com")
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8501").split(",")
    if origin.strip()
]

# Environment & Observability
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()

# FastAPI Security, JWT & CORS
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION_SUPER_SECRET_KEY")
JWT_ALGORITHM = "HS256"
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").strip().lower() == "true"

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8501").split(",")
    if origin.strip()
]

# Redis & Session Retention
REDIS_URL = os.getenv("REDIS_URL", "").strip()
SESSION_CLEANUP_INTERVAL_HOURS = int(os.getenv("SESSION_CLEANUP_INTERVAL_HOURS", "6"))
SESSION_MAX_AGE_HOURS = int(os.getenv("SESSION_MAX_AGE_HOURS", "24"))


LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
LLM_FALLBACK_PROVIDER = os.getenv("LLM_FALLBACK_PROVIDER", "").strip().lower()

OPENAI_COMPAT_BASE_URL = os.getenv("OPENAI_COMPAT_BASE_URL", "https://api.groq.com/openai/v1").strip().rstrip("/")
OPENAI_COMPAT_API_KEY = os.getenv("OPENAI_COMPAT_API_KEY", "").strip()
OPENAI_COMPAT_MODEL = os.getenv("OPENAI_COMPAT_MODEL", "qwen/qwen3.8-27b").strip()
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))
