"""SSH key management: effective path resolution and auto-generation."""
import os
from pathlib import Path

import paramiko

FALLBACK_KEY_PATH = Path("/app/data/.ssh/id_ed25519")


def get_effective_private_key_path() -> str:
    """Return the path to use for SSH (may not exist if generation failed)."""
    env_path = os.environ.get("SSH_PRIVATE_KEY_PATH", "/app/.ssh/id_ed25519").strip()
    if env_path and Path(env_path).is_file():
        return env_path
    if FALLBACK_KEY_PATH.is_file():
        return str(FALLBACK_KEY_PATH)
    return str(FALLBACK_KEY_PATH)


def ensure_ssh_keys() -> None:
    """Generate Ed25519 key pair if no key exists at configured or fallback path."""
    if os.environ.get("AUTO_GENERATE_KEYS", "true").lower() in ("false", "0", "no"):
        return

    env_path = os.environ.get("SSH_PRIVATE_KEY_PATH", "/app/.ssh/id_ed25519").strip()
    if env_path and Path(env_path).is_file():
        return
    if FALLBACK_KEY_PATH.is_file():
        return

    FALLBACK_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    key = paramiko.Ed25519Key.generate()
    key.write_private_key_file(str(FALLBACK_KEY_PATH))
    FALLBACK_KEY_PATH.chmod(0o600)
