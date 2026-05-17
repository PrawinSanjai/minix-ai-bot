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

### 2. Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn main:api --reload --port 8000
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, create an account, and start talking.

## Running Without Internet

No API key needed. Minix works fully offline with curated responses — you get emotional support without any external service costs.
