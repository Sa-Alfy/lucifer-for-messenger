# Profile Module

## Purpose
Tracks user profile and persona-related state used to personalize replies.

## Responsibilities
- Stores per-user persona selection.
- Maintains user presence and last-seen metadata.
- Supports admin-facing user listing and moderation.

## Main files
- services/personas.py
- services/admin.py

## Entry points
- handle_persona_command()
- list_users()
- get_stats_dict()

## Dependencies
- PostgreSQL user table
- services.messenger_api

## Data flow
When a user changes persona, the selected value is persisted in the user row and used for subsequent AI replies.

## Related APIs
- Messenger command /persona
- Admin user listing API

## Related database tables
- users

## Known issues
- Persona handling is still fairly lightweight and not yet split into a full profile service.

## Future improvements
- Expand profile state into richer preferences and memory settings.
