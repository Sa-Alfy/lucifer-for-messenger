# Lucifer — Facebook Messenger AI Assistant

> A production-grade AI assistant bot for Facebook Messenger, built with FastAPI, Groq (text + transcription + translation), Gemini (vision + OCR), and Hugging Face FLUX (image generation). Deployed on Render with Neon Postgres and Upstash Redis.

---

## Features (Current — Phase 4)

| Capability | Details |
|---|---|
| 🤖 **AI Chat** | Powered by Groq (`openai/gpt-oss-120b`, fallback: `gpt-oss-20b`) |
| 🖼️ **Image Understanding** | Send any photo — Gemini 2.5 Flash describes and responds to it |
| 🎨 **Image Generation** | `/image <prompt>` — generates via HF FLUX.1-schnell, hosted on Supabase |
| 🔍 **OCR** | `/ocr` + a photo attachment — extracts literal text via Gemini vision |
| 🌐 **Translation** | `/translate <language> <text>` — powered by Groq |
| 💡 **AI Text Tools** | `/explain`, `/summarize`, `/rewrite` — via Groq |
| 🎙️ **Voice Messages** | Voice input auto-transcribed via Groq Whisper; flows into normal chat |
| 🎭 **Personas** | Switch AI personality on demand with `/persona` |
| 💬 **Conversation History** | Per-user rolling history stored in Redis |
| 🔁 **Idempotent Webhooks** | Duplicate event protection via Postgres atomic upsert |
| 🚦 **Rate Limiting** | Per-user burst protection via Redis |
| 🔒 **Signature Verification** | All inbound webhooks verified with `X-Hub-Signature-256` |
| ⚡ **Feature Flags** | Per-feature toggles in Postgres — disable any capability without a redeploy |
| 🏥 **Health Check** | `/healthz` verifies Postgres + Redis connectivity |

---

## Bot Commands

| Command | Description |
|---|---|
| `/persona` | List all available personas |
| `/persona <name>` | Switch to a different personality |
| `/image <description>` | Generate an image from a text prompt |
| `/ocr` *(+ photo attachment)* | Extract all text from the attached photo |
| `/translate <language> <text>` | Translate text into any language |
| `/explain <text>` | Get a clear, simple explanation |
| `/summarize <text>` | Get a concise summary of key points |
| `/rewrite <text>` | Rewrite text to be clearer and better written |

**Available Personas:** `default` · `teacher` · `friend` · `coder`

> **Voice messages** are handled automatically — no command needed. A spoken question gets a persona-aware AI reply. A spoken `/persona teacher` switches persona just like a typed one.

---

## Feature Flags

Every AI capability is individually gated by a row in the `feature_flags` Postgres table. Set `enabled = false` for any key to disable that feature without redeploying.

| Flag key | Controls |
|---|---|
| `ai_chat` | Main AI chat replies + AI text tools (`/explain`, `/summarize`, `/rewrite`) |
| `image_gen` | `/image` command — Hugging Face generation + Supabase upload |
| `ocr` | `/ocr` command — Gemini vision text extraction |
| `translate` | `/translate` command — Groq translation |
| `voice_input` | Voice message transcription — Groq Whisper |

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
| **Image Generation** | Hugging Face FLUX.1-schnell (Apache 2.0) |
| **Transcription** | Groq Whisper (`whisper-large-v3-turbo`) |
| **Image Storage** | Supabase Storage (`generated-images` bucket) |
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
│   ├── event_processor.py     # Central pipeline — command dispatch + voice routing
│   ├── groq_client.py         # Groq async wrapper (chat + Whisper transcription)
│   ├── gemini_vision.py       # Gemini vision wrapper (image understanding + OCR)
│   ├── image_gen.py           # HF FLUX.1-schnell image generation (run_in_executor)
│   ├── storage.py             # Supabase Storage upload → public URL
│   ├── ocr.py                 # OCR adapter (reuses gemini_vision with OCR prompt)
│   ├── translate.py           # Translation via Groq
│   ├── ai_tools.py            # Explain / summarize / rewrite via Groq
│   ├── messenger_api.py       # Facebook Send API (text + image URL)
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
| `HF_API_KEY` | ✅ Phase 4 | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) |
| `SUPABASE_URL` | ✅ Phase 4 | Supabase → Project → Settings → API |
| `SUPABASE_SERVICE_KEY` | ✅ Phase 4 | Supabase → Project → Settings → API → `service_role` key |

### 4. Create the Supabase Storage bucket *(Phase 4 prerequisite)*

In the Supabase dashboard: **Storage → New bucket → name: `generated-images` → Public: ✅**

This is a one-time manual step. The `/image` command will fail without it.

### 5. Run database migrations

Creates all required tables. Safe to run multiple times.

```bash
python scripts/run_migrations.py
```

### 6. Start the development server

```bash
uvicorn main:app --reload
```

### 7. Verify connectivity

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
| **4** | ✅ Done | Image generation, OCR, translation, text tools, voice transcription |
| **5** | 🔜 Next | Utility tools — weather, currency |
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
HF_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
```

---

## License

MIT
