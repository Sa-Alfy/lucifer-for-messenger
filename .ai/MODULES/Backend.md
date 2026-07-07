# Backend Module

## Purpose
Provides the FastAPI entrypoint, configuration, routing, and application lifecycle for the service.

## Responsibilities
- Starts and stops database and Redis connectivity.
- Exposes health checks.
- Mounts webhook and admin dashboard routes.

## Main files
- main.py
- config.py

## Entry points
- FastAPI app in main.py
- /healthz endpoint
- /webhook routes
- /admin routes

## Dependencies
- db.postgres
- db.redis_client
- handlers.webhook
- handlers.admin_dashboard

## Data flow
Incoming requests enter the FastAPI app, are processed by handlers, and then routed to services or persistence layers.

## Related APIs
- Messenger webhook endpoints
- Admin dashboard endpoints

## Related database tables
- users
- feature_flags
- processed_webhook_events

## Known issues
- The app relies on live infrastructure and environment configuration during startup.

## Future improvements
- Add richer observability and health metrics.
- Consider a more formal startup dependency graph if the service grows.
