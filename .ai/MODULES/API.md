# API Module

## Purpose
Wraps outbound calls to the Facebook Messenger Send API and ensures reliability for text, quick replies, and image messages.

## Responsibilities
- Send text replies in chunks when the Messenger limit is exceeded.
- Send quick replies with structured payloads.
- Send image attachments using hosted URLs.
- Apply retry strategies for transient network and 5xx failures.

## Main files
- services/messenger_api.py

## Entry points
- send_text_message()
- send_quick_replies()
- send_image_url()

## Dependencies
- httpx
- tenacity
- config.settings

## Data flow
The event processor calls the Messenger API wrapper to send user-facing answers after AI or command handling completes.

## Related APIs
- Facebook Graph API v25.0

## Related database tables
- None directly; relies on settings and runtime state.

## Known issues
- The implementation is intentionally strict about retries and uses a pinned Graph API version.

## Future improvements
- Add richer telemetry for send failures and message delivery outcomes.
