"""
scripts/sign_test_payload.py — Local signature test helper.

Generates the X-Hub-Signature-256 header value for a given payload file,
so you can test webhook signature verification locally without going through
the Facebook dashboard.

Usage:
    python scripts/sign_test_payload.py <payload_file> <app_secret>

Example:
    python scripts/sign_test_payload.py tests/fixtures/sample_message_event.json YOUR_APP_SECRET

Then send to the local server:
    curl -X POST http://localhost:8000/webhook \\
         -H "Content-Type: application/json" \\
         -H "X-Hub-Signature-256: $(python scripts/sign_test_payload.py tests/fixtures/sample_message_event.json YOUR_APP_SECRET)" \\
         --data-binary @tests/fixtures/sample_message_event.json

Run it twice with the same payload to verify the idempotency guarantee:
the second run should produce no new row in processed_webhook_events and no
second reply.
"""

import hashlib
import hmac
import sys


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "Usage: python scripts/sign_test_payload.py <payload_file> <app_secret>",
            file=sys.stderr,
        )
        sys.exit(1)

    payload_path = sys.argv[1]
    app_secret = sys.argv[2]

    with open(payload_path, "rb") as f:
        raw = f.read()

    sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    print(f"sha256={sig}")


if __name__ == "__main__":
    main()
