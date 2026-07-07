# Directory Structure

## Repository layout
```text
.
├── main.py                  # FastAPI app entry point and health checks
├── config.py                # Environment-driven application settings
├── requirements.txt         # Python dependencies
├── Procfile                 # Process start command for deployment
├── render.yaml              # Render deployment config
├── runtime.txt              # Python runtime version
├── .env.example             # Environment variable template
├── db/                      # Database connection and lifecycle helpers
├── handlers/                # FastAPI routers and request entrypoints
├── migrations/              # SQL schema migrations
├── scripts/                 # Utility scripts for local operations
├── services/                # Core business logic and provider integrations
├── static/                  # Admin dashboard HTML assets
├── tests/                   # pytest coverage for infrastructure and features
├── utils/                   # Shared utilities such as logging and security
└── Telegrame_Bot-Lucifer--main/  # Legacy/related historical bot code
```

## Important folders
- db/: contains the asyncpg pool and Redis client wrappers.
- handlers/: contains webhook and admin dashboard routers.
- services/: holds the operational logic for AI, messaging, storage, weather, currency, and admin behavior.
- migrations/: keeps the database schema evolution explicit and repeatable.
- scripts/: provides migration and payload-signing helpers for local development.
- tests/: documents expected behavior and helps protect critical flows during change.
- utils/: contains reusable security and logging helpers.

## Notes on structure
The codebase is intentionally split by responsibility. This makes it easier for future AI agents to localize changes without reading unrelated code.
