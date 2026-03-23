import hashlib
import hmac

from sidclaw.webhooks import verify_webhook_signature


def _sign(payload: str, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def test_verify_valid_signature():
    payload = '{"event": "approval.approved"}'
    secret = "whsec_test123"
    sig = _sign(payload, secret)
    assert verify_webhook_signature(payload, sig, secret) is True


def test_verify_invalid_signature():
    payload = '{"event": "approval.approved"}'
    assert verify_webhook_signature(payload, "sha256=invalid", "secret") is False


def test_verify_tampered_payload():
    payload = '{"event": "approval.approved"}'
    secret = "whsec_test123"
    sig = _sign(payload, secret)
    assert verify_webhook_signature(payload + "tampered", sig, secret) is False


def test_verify_missing_prefix():
    assert verify_webhook_signature("payload", "invalid_no_prefix", "secret") is False


def test_verify_bytes_payload():
    payload = b'{"event": "test"}'
    secret = "whsec_test"
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(payload, expected, secret) is True
