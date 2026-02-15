"""SSH key management: effective path resolution and auto-generation."""
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

logger = logging.getLogger(__name__)

# Derive from AUTHORIZED_KEYS_PATH when set (Docker); else use app data dir (local dev)
def _fallback_key_path() -> Path:
    auth_path = os.environ.get("AUTHORIZED_KEYS_PATH")
    if auth_path:
        return Path(auth_path).parent / ".ssh" / "id_ed25519"
    return Path(__file__).parent / "data" / ".ssh" / "id_ed25519"


def get_effective_private_key_path() -> str:
    """Return the path to use for SSH (may not exist if generation failed)."""
    env_path = os.environ.get("SSH_PRIVATE_KEY_PATH", "/app/.ssh/id_ed25519").strip()
    if env_path and Path(env_path).is_file():
        return env_path
    fallback = _fallback_key_path()
    if fallback.is_file():
        return str(fallback)
    return str(fallback)


def ensure_ssh_keys() -> None:
    """Generate Ed25519 key pair if no key exists at configured or fallback path."""
    if os.environ.get("AUTO_GENERATE_KEYS", "true").lower() in ("false", "0", "no"):
        return

    env_path = os.environ.get("SSH_PRIVATE_KEY_PATH", "/app/.ssh/id_ed25519").strip()
    if env_path and Path(env_path).is_file():
        return
    fallback = _fallback_key_path()
    if fallback.is_file():
        return

    try:
        fallback.parent.mkdir(parents=True, exist_ok=True)
        key = ed25519.Ed25519PrivateKey.generate()
        pem_bytes = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=serialization.NoEncryption(),
        )
        fallback.write_bytes(pem_bytes)
        fallback.chmod(0o600)
    except Exception as e:
        logger.warning("Could not auto-generate SSH key: %s", e)
