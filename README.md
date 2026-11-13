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

Start Redis for shared recent-chat caching and rate limiting:
```bash
docker run -d --name minix-cache -p 127.0.0.1:6379:6379 -v minix-redis-data:/data redis:7-alpine redis-server --appendonly yes
```

Redis also carries the worker queue and live reply events. The PostgreSQL outbox is the durable source of queued work; Redis Streams can be rebuilt from it if Redis loses entries.

### 2. Backend
```bash
cd backend
poetry lock
poetry install --no-root
cp .env.example .env
# Generate a key with: python -c "import secrets; print(secrets.token_urlsafe(48))"
# Put the generated value in SECRET_KEY in .env before starting the server.
poetry run uvicorn main:api --reload --port 8000
```

Run the chat worker in a second terminal from `backend`:
```bash
poetry run python worker.py
```

The API accepts messages with an idempotency key, stores each message and job in PostgreSQL, and publishes jobs through an outbox to a Redis Stream. The worker pool generates replies and sends tokens over authenticated server-sent events. Failed work is retried with backoff and eventually recorded in a dead-letter stream. Run additional worker processes to increase throughput; `CHAT_WORKER_CONCURRENCY` sets the in-process limit per worker.

Use Python 3.13 or newer. `GEMINI_API_KEY` is optional for startup, but chat replies require a working Gemini API key.
Redis caches per-user conversation lists and details, coordinates per-conversation writes, shares rate limits, and transports jobs/events. API requests can still be queued while Redis is temporarily unavailable; workers require Redis to run. Database pool settings apply to each API and worker process, so keep PostgreSQL's connection limit above `(DB_POOL_SIZE + DB_MAX_OVERFLOW) × (API process count + worker process count)`, with room for administration and other services.

Operational settings, including retry count, worker concurrency, and summary cadence, are listed in `backend/.env.example`. `/health-check` reports Redis availability and `/metrics` exposes shared request and chat-job counters and latency histograms in Prometheus format.

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, create an account, and start talking.

## Running Without Gemini

Without a Gemini API key, Minix displays a service-unavailable reply. PostgreSQL is still required for accounts and saved conversations.
