-- migrations/0001_init.sql
-- Phase 1: core tables only.
-- All statements are idempotent — safe to run multiple times.

CREATE TABLE IF NOT EXISTS users (
    id               BIGSERIAL PRIMARY KEY,
    psid             TEXT UNIQUE NOT NULL,
    first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    persona          TEXT NOT NULL DEFAULT 'default',
    is_blocked       BOOLEAN NOT NULL DEFAULT false,
    message_count    BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS feature_flags (
    key         TEXT PRIMARY KEY,
    enabled     BOOLEAN NOT NULL DEFAULT true,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processed_webhook_events (
    event_id      TEXT PRIMARY KEY,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed feature flags.
-- daraz is disabled by default — the scraper is paused, not removed.
-- Flip to true in the DB whenever it's ready to re-enable; no schema change needed.
INSERT INTO feature_flags (key, enabled) VALUES
    ('ai_chat',      true),
    ('image_gen',    true),
    ('downloader',   true),
    ('ocr',          true),
    ('translate',    true),
    ('voice_input',  true),
    ('weather',      true),
    ('currency',     true),
    ('daraz',        false)
ON CONFLICT (key) DO NOTHING;
