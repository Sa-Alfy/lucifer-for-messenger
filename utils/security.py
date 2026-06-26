"""
utils/security.py — Facebook webhook signature verification.

Facebook signs every POST request body with HMAC-SHA256 using the app secret
and sends the result as the X-Hub-Signature-256 header.

Critical: verification MUST run against the raw request bytes, before any
JSON parsing. Re-serialising a parsed dict can produce different byte sequences
(e.g. different key ordering or spacing), causing legitimate signatures to fail.
"""

import hashlib
import hmac


def verify_fb_signature(
    raw_body: bytes,
    signature_header: str | None,
    app_secret: str,
) -> bool:
    """
    Return True if the request signature is valid; False otherwise.

    Args:
        raw_body:         The exact bytes received from Facebook (do not decode).
        signature_header: Value of the X-Hub-Signature-256 header (may be None).
        app_secret:       The Facebook App Secret from settings.

    Uses hmac.compare_digest (constant-time) instead of == to prevent
    timing-based side-channel attacks that could reveal partial secret info.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    provided = signature_header.split("sha256=", 1)[1]

    # constant-time comparison — never use == here
    return hmac.compare_digest(expected, provided)
