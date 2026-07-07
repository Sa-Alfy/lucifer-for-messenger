# AI Working Rules

## Coding conventions
- Prefer small, explicit functions over large monolithic blocks.
- Preserve async patterns; this codebase is designed around async I/O.
- Keep error handling explicit and user-safe.
- Avoid introducing synchronous network calls into async flows.

## Naming conventions
- Use descriptive Python function and module names.
- Keep existing service names and route names consistent with current patterns.
- Preserve environment variable names from config.py and .env.example.

## Folder organization
- Keep web entrypoints in handlers/.
- Keep domain logic in services/.
- Keep persistence code in db/.
- Keep shared utilities in utils/.
- Keep schema changes in migrations/.

## Architectural patterns
- Preserve the webhook-first, background-processing model.
- Maintain idempotency for webhook events.
- Use feature flags for optional capabilities.
- Prefer Redis for ephemeral state and Postgres for durable state.

## Reusable components
- Use the existing logger utilities rather than introducing ad-hoc logging.
- Reuse the existing Messenger API wrapper for outbound messages.
- Reuse the feature-flag helpers and admin helpers when adding new capabilities.

## Things AI should NEVER do
- Do not change production behavior without a clear reason.
- Do not bypass signature verification, idempotency, or rate limiting.
- Do not silently change AI provider model selection unless explicitly requested.
- Do not rename or refactor modules broadly without justification.

## Things AI should ALWAYS do
- Read the relevant service and handler before editing.
- Preserve existing environment-variable conventions.
- Document new behavior in the knowledge base when it materially changes the architecture.
- Verify behavior with the relevant tests or a targeted local check.

## Rules for editing
- Make the smallest change that solves the stated problem.
- Keep edits scoped to the relevant module.
- Avoid unrelated formatting churn.

## Rules for adding features
- Add feature flags when the capability could be toggled independently.
- Follow the existing command/handler pattern for new user-facing commands.
- Keep deploy-time configuration in environment variables.

## Rules for debugging
- Trace the request from webhook to processor to outbound reply.
- Check Postgres, Redis, and provider configuration before assuming app code is at fault.
- Preserve logging context so failures remain actionable.

## Rules for writing documentation
- Prefer concise, reference-oriented summaries over long prose.
- Cross-reference related modules and files.
- Keep docs aligned with the code rather than with outdated assumptions.
