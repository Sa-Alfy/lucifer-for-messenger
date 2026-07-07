# Database Module

## Purpose
Defines and manages the durable and transient persistence layers used by the bot.

## Responsibilities
- Establish and close the PostgreSQL connection pool.
- Provide Redis client lifecycle helpers.
- Support health checks for both storage services.

## Main files
- db/postgres.py
- db/redis_client.py

## Entry points
- init_pool()
- init_redis()
- get_pool()
- get_redis()
- ping()

## Dependencies
- asyncpg
- redis.asyncio
- tenacity

## Data flow
The application uses Postgres for durable business state and Redis for short-lived counters, history, and windowing.

## Related APIs
- Health checks in main.py
- Admin stats and moderation endpoints

## Related database tables
- users
- feature_flags
- processed_webhook_events

## Known issues
- The current implementation assumes the database layer is available during startup.

## Future improvements
- Add stronger connection pooling observability and retry metrics.
