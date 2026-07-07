# Known Issues and Technical Debt

## Observed issues
- The repository contains a legacy sibling directory, Telegrame_Bot-Lucifer--main, which may cause confusion for future contributors.
- The project includes generated output under graphify-out, which is likely useful for inspection but may be noisy for day-to-day development.
- The codebase uses multiple external providers; failures in any of them can cause partial feature degradation.
- Some test stubs use placeholder pass statements, which indicate incomplete coverage or intentionally simplified test scaffolding.

## Areas to watch
- The webhook processing path is intentionally asynchronous and backgrounded; this improves responsiveness but may lose events during process restarts.
- Admin dashboard and messaging integrations depend on live external credentials, so local development requires environment setup.
- AI provider selection is hard-coded in several modules; changing providers or models requires coordinated updates.

## Potential improvements
- Add more explicit operational monitoring and observability.
- Consolidate or document the legacy bot directory separately.
- Add more targeted tests around failure modes and provider retries.
- Consider a durable queue if webhook throughput grows significantly.
