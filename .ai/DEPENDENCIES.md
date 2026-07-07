# Dependencies and Integrations

## Runtime dependencies
- Python 3.11
- FastAPI: main HTTP framework and routing layer
- Uvicorn: ASGI server for local and deployment execution
- asyncpg: async PostgreSQL driver
- redis: async Redis client
- pydantic-settings: environment-driven settings management
- tenacity: retry logic for flaky external services
- httpx: async HTTP client for provider and Messenger API calls

## AI and media dependencies
- groq: chat completions, tool calling, transcription
- google-genai: Gemini-based vision/OCR support
- huggingface_hub: image-generation integration
- Pillow: image handling support
- python-multipart: multipart form parsing for FastAPI uploads

## Data and hosting dependencies
- PostgreSQL: durable user and event state
- Redis: ephemeral state, counters, history, and rate limits
- Supabase Storage: hosted public image uploads
- Render: deployment target

## Messenger and external services
- Facebook Messenger Graph API: outbound replies and event delivery
- OpenWeatherMap: weather lookup
- Frankfurter ECB API: currency conversion
- Supabase management API: storage uploads and admin-backed operations

## Why these dependencies matter
They support the current architecture: a webhook-driven service that must stay responsive while coordinating multiple networked AI and storage backends.
