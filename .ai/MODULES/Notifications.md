# Notifications Module

## Purpose
Handles user-facing outbound notifications and message delivery patterns.

## Responsibilities
- Compose and send text and image replies.
- Potentially surface admin and feature-related notices.

## Main files
- services/messenger_api.py
- services/event_processor.py

## Entry points
- send_text_message()
- send_quick_replies()
- send_image_url()

## Dependencies
- Facebook Messenger Send API
- config.settings

## Data flow
Notifications are produced by the event processor and delivered via the Messenger wrapper.

## Related APIs
- Messenger Send API

## Related database tables
- None directly.

## Known issues
- Reliability depends heavily on provider and network conditions.

## Future improvements
- Add richer delivery status tracking and fallback behavior.
