# Messaging Module

## Purpose
Coordinates the inbound Messenger event pipeline, command dispatch, AI reply generation, and outbound responses.

## Responsibilities
- Validates and deduplicates webhook events.
- Recognizes audio, image, and text inputs.
- Routes commands such as /persona, /image, /ocr, /translate, /weather, /currency, and /help.
- Applies rate limiting, feature flags, and personas.

## Main files
- services/event_processor.py
- handlers/webhook.py

## Entry points
- process_messaging_event()
- receive_webhook()
- verify_webhook()

## Dependencies
- services.admin
- services.chat_history
- services.feature_flags
- services.groq_client
- services.messenger_api
- services.personas
- services.rate_limit
- services.weather
- services.currency
- services.translate

## Data flow
Messenger events enter through the webhook handler, pass through the event processor, and then trigger AI calls, database lookups, and outbound replies.

## Related APIs
- Facebook Messenger webhook
- Messenger Send API
- Groq and Gemini providers

## Related database tables
- users
- processed_webhook_events
- feature_flags

## Known issues
- Background processing can lose events if the process restarts between acceptance and execution.

## Future improvements
- Add durable queue support for higher reliability.
