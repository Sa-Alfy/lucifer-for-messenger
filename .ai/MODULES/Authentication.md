# Authentication Module

## Purpose
Handles the trust boundary for incoming webhook requests and dashboard access.

## Responsibilities
- Verifies Facebook webhook signatures.
- Protects admin dashboard sessions with signed cookies.
- Checks admin claim secrets and login attempts.

## Main files
- utils/security.py
- handlers/admin_dashboard.py
- services/admin.py

## Entry points
- verify_fb_signature()
- create_session_token()
- verify_session_token()
- claim_admin()

## Dependencies
- hmac
- config.settings

## Data flow
Incoming webhooks must pass signature validation before any processing proceeds. Dashboard access uses signed session tokens and server-side secret checks.

## Related APIs
- Facebook webhook verification
- Admin dashboard HTTP routes

## Related database tables
- users

## Known issues
- Admin access depends on environment-backed secrets and careful deployment configuration.

## Future improvements
- Add stronger audit logging around admin claims and login events.
