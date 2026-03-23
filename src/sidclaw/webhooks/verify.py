from __future__ import annotations

import hashlib
import hmac


def verify_webhook_signature(payload: str | bytes, signature: str, secret: str) -> bool:
    """Verify a SidClaw webhook signature.

    Args:
        payload: Raw request body (string or bytes)
        signature: Value of the X-Webhook-Signature header
        secret: Your webhook endpoint's secret

    Returns:
        True if the signature is valid
    """
    if not signature.startswith("sha256="):
        return False

    if isinstance(payload, str):
        payload = payload.encode("utf-8")

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(signature, expected)
