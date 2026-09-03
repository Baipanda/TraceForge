"""Gitea webhook signature verification (HMAC-SHA256)."""

from __future__ import annotations

import hashlib
import hmac


def verify_gitea_signature(*, body: bytes, secret: str, signature_header: str | None) -> bool:
    """Return True when signature matches, or when secret is empty (dev open mode)."""
    if not secret:
        return True
    if not signature_header:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    provided = signature_header.strip().lower()
    if provided.startswith("sha256="):
        provided = provided[7:]
    return hmac.compare_digest(expected, provided)
