# Minix

Your personal emotional AI companion. A safe, judgment-free space to express your feelings, clear your mind, and feel heard.

## Why Minix?

Life gets overwhelming. Sometimes you just need someone to talk to — without judgment, without schedules, without pretending to be okay. Minix is that space.

- **Talk about anything** — stress, anxiety, relationships, career, or just your day
- **Adapts to you** — choose between Friendly, Motivational, or Listener tone
- **Remembers what matters** — references past conversations so you don't have to repeat yourself
- **Always available** — no appointments, no waiting, no pressure
- **Your privacy** — conversations stay yours

## Quick Start

### 1. Database
```bash
docker run -d --name minix-db -e POSTGRES_PASSWORD=root -p 5432:5432 pgvector/pgvector:pg17
docker exec minix-db psql -U postgres -c "CREATE DATABASE minix_db;"
```

The backend uses PostgreSQL with the pgvector extension. Keep the database container running while using Minix.

Start Redis for recent-chat caching, rate limiting, and live reply updates:
```bash
docker run -d --name minix-cache -p 127.0.0.1:6379:6379 -v minix-redis-data:/data redis:7-alpine redis-server --appendonly yes
```

Chat jobs are stored directly in PostgreSQL. Redis is used for caching, rate limits, and reply updates.

### 2. Backend
```bash
cd backend
poetry lock
poetry install --no-root
cp .env.example .env
# Generate a key with: python -c "import secrets; print(secrets.token_urlsafe(48))"
# Put the generated value in SECRET_KEY in .env before starting the server.
poetry run uvicorn main:api --reload --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*
```

Keep port `8000` reachable only from the gateway. Start the gateway in another terminal:
```bash
docker compose -f gateway/docker-compose.yml up -d
```

Run the chat worker in a second terminal from `backend`:
```bash
poetry run python worker.py
```

The API saves each message and job to PostgreSQL. Workers claim pending jobs from the database, generate replies, and send tokens over authenticated server-sent events. Failed jobs are retried up to `CHAT_JOB_MAX_ATTEMPTS`. Run additional worker processes to increase throughput; `CHAT_WORKER_CONCURRENCY` controls the number of jobs each worker handles at once.

Use Python 3.13 or newer. `GEMINI_API_KEY` is optional for startup, but chat replies require a working Gemini API key.
Redis caches per-user conversation lists and details, coordinates per-conversation writes, shares rate limits, and transports live reply events. Workers require both PostgreSQL and Redis. Database pool settings apply to each API and worker process, so keep PostgreSQL's connection limit above `(DB_POOL_SIZE + DB_MAX_OVERFLOW) × (API process count + worker process count)`, with room for administration and other services.

Operational settings, including retry count and worker concurrency, are listed in `backend/.env.example`. `/health-check` reports Redis availability and `/metrics` exposes basic request and chat-job metrics.

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, create an account, and start talking.

## API protection

Minix uses Nginx as an API Gateway on port `8080`. It forwards requests to FastAPI on port `8000`. FastAPI also keeps its own protections enabled:

- **Routing:** Nginx is the public entry point and forwards `/auth`, `/users`, and `/chat` requests to FastAPI.
- **Rate and size limits:** Nginx limits requests by client IP and caps request bodies. FastAPI adds a shared Redis rate limit and its own body-size check.
- **CORS and host validation:** FastAPI accepts only configured browser origins and hostnames. Set `CORS_ALLOW_ORIGINS` and `ALLOWED_HOSTS` for your deployment.
- **Request IDs and headers:** Nginx creates a request ID; FastAPI returns it in `X-Request-ID` and includes it in app logs. FastAPI also adds security headers.
- **Streaming:** Nginx disables response buffering so chat tokens can stream to the browser.
- **Metrics:** `/metrics` exposes basic request and chat-job counters.

The included Nginx config targets a backend running on the Docker host for local development. In production, point its upstream at the private backend service and do not expose port `8000` publicly.

## Running Without Gemini

Without a Gemini API key, Minix displays a service-unavailable reply. PostgreSQL is still required for accounts and saved conversations.
