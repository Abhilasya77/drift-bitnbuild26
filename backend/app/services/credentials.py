"""Temporary credential helpers (schema sections 13-14).

The QR token is derived with HMAC from the credential id + a server secret, so we never store
the raw token (only its SHA-256 hash) but can still re-show the QR later.
"""
import base64
import hashlib
import hmac
import io
import json
import secrets

import qrcode

from .. import config


def new_public_id() -> str:
    raw = secrets.token_hex(4).upper()
    return f"ICP-{raw[:4]}-{raw[4:]}"


def token_for(credential_id: str) -> str:
    digest = hmac.new(config.CREDENTIAL_SECRET.encode(), credential_id.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_url(token: str) -> str:
    return f"{config.VERIFY_BASE_URL}/{token}"


def qr_png(text: str) -> bytes:
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def attestation_hash(public_id: str, issued_at: str, expires_at: str, state: str) -> str:
    """Non-sensitive fingerprint for the optional on-chain attestation. No names, DOB or numbers."""
    payload = json.dumps({"credential": public_id, "issued_at": issued_at, "expires_at": expires_at,
                          "state": state, "issuer": "identity-continuity-platform"}, sort_keys=True)
    return "0x" + hashlib.sha256(payload.encode()).hexdigest()
