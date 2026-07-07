# Project Overview

This repository implements a production-oriented Messenger AI assistant service for conversational automation, AI-powered tool use, and admin moderation. The active application is a Python/FastAPI backend that receives webhook events from Facebook Messenger, processes them through a central event pipeline, and replies using external AI services.

## What it does
- Receives inbound Messenger messages and voice notes.
- Routes commands such as /persona, /image, /ocr, /translate, /weather, and /currency.
- Uses Groq for chat and tool calling, Gemini for vision/OCR, and Hugging Face for image generation.
- Stores user and feature-flag state in PostgreSQL and short-lived state in Redis.
- Exposes an internal admin dashboard for moderation and feature toggles.

## Technology stack
- Language: Python 3.11
- Framework: FastAPI + Uvicorn
- Database: PostgreSQL via asyncpg
- Cache: Redis via redis.asyncio
- AI providers: Groq, Google Gemini, Hugging Face
- Storage: Supabase Storage
- Deployment: Render
- Testing: pytest

## Current maturity
This is a Phase 6b-style MVP / production-ready backend foundation with live webhook handling, admin controls, feature flags, and AI workflows already implemented.
