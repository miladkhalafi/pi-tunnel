"""One-time tokens for WebSocket terminal auth (Basic Auth doesn't send with WS)."""
import time
import uuid

_tokens = {}


def create_token(pi_id: int, ttl: int = 120) -> str:
    token = uuid.uuid4().hex
    _tokens[token] = (pi_id, time.time() + ttl)
    return token


def validate_token(token: str, pi_id: int) -> bool:
    if not token or token not in _tokens:
        return False
    stored_id, expiry = _tokens[token]
    del _tokens[token]
    return stored_id == pi_id and time.time() < expiry
