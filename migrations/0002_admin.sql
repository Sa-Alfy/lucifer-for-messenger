-- migrations/0002_admin.sql
-- Phase 6a: admin bootstrap column on users.

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false;
