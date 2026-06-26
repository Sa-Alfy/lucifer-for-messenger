# Lucifer — Facebook Messenger AI Assistant

> A production-grade AI assistant bot for Facebook Messenger, built with FastAPI, Groq (text), and Gemini (vision). Deployed on Render with Neon Postgres and Upstash Redis.

---

## Features (Current — Phase 3)

| Capability | Details |
|---|---|
| 🤖 **AI Chat** | Powered by Groq (`openai/gpt-oss-120b`, fallback: `gpt-oss-20b`) |
| 🖼️ **Image Understanding** | Send any photo — Gemini 2.5 Flash describes and responds to it |
| 🎭 **Personas** | Switch AI personality on demand with `/persona` |
| 💬 **Conversation History** | Per-user rolling history stored in Redis |
| 🔁 **Idempotent Webhooks** | Duplicate event protection via Postgres atomic upsert |
| 🚦 **Rate Limiting** | Per-user burst protection via Redis |
| 🔒 **Signature Verification** | All inbound webhooks verified with `X-Hub-Signature-256` |
| ⚡ **Feature Flags** | `ai_chat` flag controls AI responses without a redeploy |
| 🏥 **Health Check** | `/healthz` verifies Postgres + Redis connectivity |

---

## Bot Commands

| Command | Description |
|---|---|
| `/persona` | List all available personas |
| `/persona <name>` | Switch to a different personality |

**Available Personas:** `default` · `teacher` · `friend` · `coder`

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Runtime** | Python 3.11 |
| **Web Framework** | FastAPI + Uvicorn |
| **Database** | PostgreSQL via asyncpg (Neon) |
| **Cache / History** | Redis via redis.asyncio (Upstash) |
| **Text AI** | Groq (`openai/gpt-oss-120b`) |
| **Vision AI** | Google Gemini 2.5 Flash |
| **Hosting** | Render (Web Service) |
| **Retry Logic** | Tenacity |
| **Config** | pydantic-settings |

---

## Project Structure

```
.
├── main.py                    # FastAPI app, lifespan, /healthz
├── config.py                  # Typed settings (pydantic-settings)
├── requirements.txt
├── Procfile                   # Render start command
├── render.yaml                # Render deployment config
├── runtime.txt                # python-3.11.9
├── .env.example               # Environment variable template
│
├── db/
│   ├── postgres.py            # asyncpg pool with tenacity retry
│   └── redis_client.py        # redis.asyncio client with retry
│
├── handlers/
│   └── webhook.py             # GET (verification) + POST (events) /webhook
│
├── migrations/
│   └── 0001_init.sql          # Schema: users, feature_flags, processed_events
│
├── scripts/
│   ├── run_migrations.py      # Safe idempotent migration runner
│   └── sign_test_payload.py   # Local webhook signature test helper
│
├── services/
│   ├── event_processor.py     # Central event pipeline (validate → AI → reply)
│   ├── groq_client.py         # Groq async wrapper with fallback model
│   ├── gemini_vision.py       # Gemini vision wrapper (single-turn)
│   ├── messenger_api.py       # Facebook Send API client
│   ├── chat_history.py        # Redis conversation history
│   ├── personas.py            # System prompt definitions per persona
│   ├── feature_flags.py       # DB-backed feature toggle queries
│   ├── messaging_window.py    # 24-hour Messenger window tracker (Redis)
│   └── rate_limit.py          # Per-user rate limit (Redis)
│
├── utils/
│   └── logger.py              # Structured stdout logger
│
└── tests/
    └── fixtures/
        └── sample_message_event.json
```

---

## Quick Start

### 1. Clone & create a virtual environment

```bash
git clone <repo-url>
cd <repo-dir>
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Fill in `.env` — see the table below for where to find each value:

| Variable | Required | Where to get it |
|---|---|---|
| `DATABASE_URL` | ✅ Phase 1 | Neon / Supabase → Project → Settings → Database → Connection string |
| `REDIS_URL` | ✅ Phase 1 | Upstash → Redis → Connection → `rediss://` URL |
| `FB_PAGE_ACCESS_TOKEN` | ✅ Phase 2 | Meta for Developers → App → Messenger → Page Access Token |
| `FB_APP_SECRET` | ✅ Phase 2 | Meta for Developers → App → Settings → Basic → App Secret |
| `FB_VERIFY_TOKEN` | ✅ Phase 2 | Any secret string you choose |
| `FB_PAGE_ID` | ✅ Phase 2 | Your Facebook Page ID |
| `GROQ_API_KEY` | ✅ Phase 3 | [console.groq.com](https://console.groq.com) |
| `GEMINI_API_KEY` | ✅ Phase 3 | [aistudio.google.com](https://aistudio.google.com) |
| `SUPABASE_URL` | Phase 6 | Supabase → Project → Settings → API |
| `SUPABASE_SERVICE_KEY` | Phase 6 | Supabase → Project → Settings → API |

### 4. Run database migrations

Creates all required tables. Safe to run multiple times.

```bash
python scripts/run_migrations.py
```

### 5. Start the development server

```bash
uvicorn main:app --reload
```

### 6. Verify connectivity

```bash
curl http://localhost:8000/healthz
# Expected: {"status":"ok","db":"ok","redis":"ok"}
```

---

## Deployment (Render)

1. Push this repo to GitHub.
2. Create a **Web Service** in Render pointing at the repo.
3. Render detects `render.yaml` and pre-fills build/start commands.
4. Set all environment variables in the Render dashboard (marked `sync: false` values are secrets — set them manually).
5. Render uses `/healthz` to gate traffic — the service only goes live when both DB and Redis respond successfully.

---

## Testing a Webhook Locally

Use the signing helper to generate a valid `X-Hub-Signature-256` header from a fixture:

```bash
# Generate signature
python scripts/sign_test_payload.py tests/fixtures/sample_message_event.json YOUR_APP_SECRET

# Send to the local server
curl -X POST http://localhost:8000/webhook \
     -H "Content-Type: application/json" \
     -H "X-Hub-Signature-256: <output from above>" \
     --data-binary @tests/fixtures/sample_message_event.json
```

Send the same request twice to confirm idempotency — the second run produces no duplicate reply.

---

## Development Roadmap

| Phase | Status | Content |
|---|---|---|
| **1** | ✅ Done | Infrastructure — FastAPI, Postgres pool, Redis client, `/healthz` |
| **2** | ✅ Done | Facebook Messenger webhook — verification + event receiver + Send API |
| **3** | ✅ Done | AI chat — Groq text, Gemini vision, personas, rate limiting, history |
| **4** | 🔜 Next | Image generation, TTS, OCR |
| **5** | ⬜ Planned | Utility tools — weather, currency, news, prayer times |
| **6** | ⬜ Planned | Admin panel and feature-flag management UI |
| **7** | ⬜ Planned | Media downloader |
| **8** | ⬜ Planned | Hardening — full test suite, observability, SLA-grade reliability |

---

## Environment Variable Reference

```env
# .env.example — copy to .env and fill in values
DATABASE_URL=postgresql://user:password@host:5432/dbname
REDIS_URL=rediss://:password@hostname:6379
ENV=dev
LOG_LEVEL=INFO
PORT=8000
FB_PAGE_ACCESS_TOKEN=
FB_APP_SECRET=
FB_VERIFY_TOKEN=
FB_PAGE_ID=
GROQ_API_KEY=
GEMINI_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
```

---

## License

MIT
