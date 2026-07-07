# Development Guide

## Prerequisites
- Python 3.11
- Access to PostgreSQL and Redis
- API keys for Groq, Gemini, Hugging Face, and Messenger-related configuration
- A local environment file based on .env.example

## Setup
1. Create and activate a virtual environment.
2. Install dependencies from requirements.txt.
3. Copy .env.example to .env and fill the required values.
4. Run the migration script to initialise the database schema.

## Running the app
- The app is started via the FastAPI entry point in main.py.
- The deployment process uses Procfile and Render configuration.

## Testing
- pytest is the expected test runner.
- The tests cover webhook flow, infrastructure health, AI integration, and admin operations.

## Configuration
- Settings are loaded from environment variables through config.py.
- Feature flags live in Postgres and can be toggled at runtime.

## Deployment
- The repository targets Render.
- Runtime configuration is expected to be supplied through the hosting environment.

## Debugging
- Start with the webhook flow and event processor pipeline.
- Verify network and provider configuration if AI features fail.
- Review Postgres and Redis health endpoints and logs.
