# 📄 RAG Resume Assistant — Enterprise-Grade CV Intelligence API

[![Python 3.12](https://shields.io)](https://python.org)
[![FastAPI](https://shields.io)](https://tiangolo.com)
[![PostgreSQL 18 + pgvector](https://shields.io)](https://github.com)
[![Redis 7](https://shields.io)](https://redis.io)
[![Docker Compose](https://shields.io)](https://docker.com)

An asynchronous, production-hardened **Retrieval-Augmented Generation (RAG)** system designed for intelligent resume search, candidate evaluation, and secure document Q&A. Built on a **Clean Layered Architecture**, it supports dual access modes (**Isolated Guest Sessions** and **RBAC-Authorized System Users**), **Hybrid Search (Vector + Keyword with RRF)**, **Guardrails-Validated SSE Streaming**, and **PII Redaction**.

---

## ✨ Key Features

- **Dual-Mode Access & Strict Isolation:**
  - **Guest Mode (`X-Session-ID`):** Upload session-scoped PDFs and query them using `hybrid`, `semantic`, or `keyword` retrieval with a restricted guest system prompt.
  - **Authorized Mode (`Bearer JWT`):** Role-Based Access Control (`admin` & `system_search`) with full access to pre-indexed Google Drive CVs and an optional toggle (`include_session_uploads`) to combine session PDFs with system documents.
- **High-Precision Hybrid Retrieval (RRF):** Executes parallel semantic vector search (`pgvector` with `HNSW` index) and PostgreSQL full-text keyword search (`GIN` index), merged via **Reciprocal Rank Fusion (RRF)**.
- **Two-Phase Validated SSE Streaming:** Streams real-time pipeline execution stages (`status`) over Server-Sent Events, validates the complete structured JSON response and citations against **Input/Output Guardrails**, and streams verified answer chunks.
- **Privacy-First Ingestion (PII Redaction):** Automatically detects and redacts sensitive candidate PII (emails, phone numbers, addresses) using **Microsoft Presidio** and **spaCy** prior to embedding and storage.
- **Distributed Scalability & Caching:** Stateless FastAPI workers backed by **Redis** atomic Lua sliding-window rate limiters, tenant-isolated SHA-256 response caching, and distributed locks (`SET NX`) for background Google Drive synchronization.

---

## 🏗️ System Architecture

```text
Client (Web / Mobile / cURL)
        │
        ▼
┌───────────────────┐
│   Nginx Proxy     │  ──► Rate Limiting, Security Headers, SSE Buffering Control
└─────────┬─────────┘
          ▼
┌───────────────────┐     ┌───────────────────────────────────────────┐
│   FastAPI App     │────►│ Redis (Rate Limiters, Cache, Sync Locks)  │
│  (Async Workers)  │     └───────────────────────────────────────────┘
└─────────┬─────────┘
          │
          ├──► Input/Output Guardrails (Prompt Injection & JSON/Citation Validation)
          ├──► Ingestion Pipeline (LlamaCloud / PyMuPDF + Presidio PII Redaction)
          ├──► Google Gemini AI (Embeddings & Structured JSON Generation)
          ▼
┌───────────────────┐
│ PostgreSQL 18     │  ──► pgvector (HNSW Cosine) + Full-Text Search (GIN)
│ (Async Pool)      │
└───────────────────┘
```

### Project Directory Structure

```text
rag_resume/
├── api/                        # FastAPI presentation & HTTP gateway layer
│   ├── main.py                 # App factory, lifespan, CORS, middlewares, exception handlers
│   ├── schemas.py              # Strict Pydantic v2 request/response contracts
│   ├── security.py             # Stateless JWT management & Redis Lua rate limiters
│   ├── dependencies.py         # Dependency injection (Auth, Guest sessions, RBAC)
│   ├── logger.py               # Structured JSON logger with automatic secret redaction
│   ├── routers/                # Domain-separated thin HTTP controllers
│   │   ├── health.py           # Cached readiness probe (/health)
│   │   ├── auth.py             # Credential login & JWT issuance (/api/v1/auth)
│   │   ├── documents.py        # Bounded PDF upload, list & IDOR-safe delete (/api/v1/documents)
│   │   ├── chat.py             # Standard JSON & SSE streaming Q&A (/api/v1/chat)
│   │   └── admin.py            # Background Google Drive sync & status (/api/v1/admin)
│   └── services/               # API orchestration & tenant-isolated caching
│       ├── chat_orchestrator.py
│       └── rag_cache.py
├── application/services/       # Core business logic (upload & document scope)
├── src/                        # RAG engine (embeddings, hybrid retrieval, answer generation)
├── parsingWays/                # PDF parsers (LlamaCloud & PyMuPDF)
├── guardrails/                 # Input/output security inspection & JSON/citation validators
├── security/                   # PBKDF2 password verification & RBAC definitions
├── prompts/                    # Role-aware system prompt registry
├── orchestrator/               # Parallel Google Drive synchronization orchestrator
├── database_utilities/         # AsyncConnectionPool & database schema migrations
├── nginx/                      # Production reverse proxy configuration (nginx.conf)
├── Dockerfile                  # Non-root Python 3.12 container definition
├── docker-compose.dev.yml      # Local development stack (hot-reload, isolated ports)
└── docker-compose.yml          # Production deployment stack (4 Uvicorn workers)
```

---

## 🛡️ Defense-in-Depth Security Controls

1. **Brute-Force & Abuse Protection:** Dual `(IP + Email)` lockout on login (`5 attempts / 15 min`) and role-aware sliding-window rate limits (`20 req/min` for guests, `60 req/min` for users) enforced atomically via Redis Lua scripts.
2. **Stream-Bounded File Uploads:** Reads uploaded PDFs in `1 MB` chunks, immediately rejecting payloads exceeding `20 MB` (`HTTP 413`) and verifying `%PDF-` magic bytes.
3. **IDOR Prevention:** Session document deletions strictly enforce `drive_file_id IS NULL` and ownership matching against `X-Session-ID`.
4. **Timing-Safe Authentication:** Constant-time PBKDF2 hash verification with dummy-hash fallback to prevent account enumeration.
5. **AI Guardrails:** Every user prompt and model output passes through `inspect_message`, strict JSON schema extraction, and source citation verification before reaching the client.
6. **Observability & Secret Redaction:** Every request is assigned a validated `X-Request-ID`, and structured JSON logs automatically redact bearer tokens, API keys, and passwords.

---

## 🚀 Quick Start (Docker Compose)

### 1. Prerequisites
- Docker & Docker Compose v2+
- Google Gemini API Key (`GEMINI_API_KEY`)
- LlamaCloud API Key (`LLAMA_CLOUD_API_KEY`, if `PARSER_TYPE=llama`)
- Google Drive OAuth credentials (`credentials.json` & `token.json`) for system document sync

### 2. Environment Configuration
Create `.env` (production/shared secrets) and `.env.development` (local dev overrides):

```bash
# Generate a strong 64-character JWT secret
python -c "import secrets; print(secrets.token_hex(32))"
```

Ensure `.env` contains:
```env
ENVIRONMENT=production
LOG_LEVEL=INFO
JWT_SECRET_KEY=<your_generated_64_char_hex_secret>
AUTH_SESSION_TTL_MINUTES=60
TRUST_PROXY_HEADERS=true
CORS_ALLOWED_ORIGINS=https://your-frontend-domain.com

DB_USER=postgres
DB_PASSWORD=<strong_db_password>
DB_NAME=resumedb
DB_POOL_MIN_SIZE=5
DB_POOL_MAX_SIZE=50

REDIS_URL=redis://redis:6379/0
GEMINI_API_KEY=<your_gemini_api_key>
LLAMA_CLOUD_API_KEY=<your_llamacloud_api_key>
PARSER_TYPE=llama
AUTHORIZED_USERS_JSON={"admin@example.com":{"password_hash":"<pbkdf2_hash>","roles":["admin"]}}
```

And `.env.development` contains:
```env
DEV_DB_USER=devuser
DEV_DB_NAME=resumedb_dev
DEV_DB_PASSWORD=devpassword
ENVIRONMENT=development
TRUST_PROXY_HEADERS=true
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8080
DB_POOL_MIN_SIZE=2
DB_POOL_MAX_SIZE=15
```

### 3. Run Local Development Environment
Starts PostgreSQL (`5434`), Redis (`6380`), FastAPI with `--reload`, and Nginx on **`http://127.0.0.1:8080`**:

```bash
docker compose --env-file .env.development -f docker-compose.dev.yml up --build -d
```
- Interactive Swagger UI: **`http://127.0.0`**
- Follow live logs: `docker compose --env-file .env.development -f docker-compose.dev.yml logs -f app`

### 4. Run Production Environment
Starts PostgreSQL (`5433`), Redis (`6379`), FastAPI (`4 workers`, `/docs` disabled), and Nginx on port **`80`**:

```bash
docker compose -f docker-compose.yml up --build -d
```

---

## 📡 API Endpoints Reference

| Method | Endpoint | Access | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Public | Cached readiness probe for PostgreSQL & Redis. |
| `POST` | `/api/v1/auth/login` | Public | Authenticate credentials and receive a `Bearer JWT`. |
| `POST` | `/api/v1/documents/upload` | Guest / User | Upload and index a PDF (`<= 20 MB`) into the current session. |
| `GET` | `/api/v1/documents/session` | Guest / User | List all PDFs uploaded in the active `X-Session-ID`. |
| `DELETE` | `/api/v1/documents/session/{id}` | Guest / User | Delete a specific session document (IDOR-protected). |
| `POST` | `/api/v1/chat/ask` | Guest / User | Ask a question and receive a Guardrails-verified JSON response. |
| `POST` | `/api/v1/chat/ask/stream` | Guest / User | Stream pipeline stages and verified answer chunks via SSE. |
| `POST` | `/api/v1/admin/sync-drive` | `admin` / `system_search` | Trigger asynchronous Google Drive CV sync (`202 Accepted`). |
