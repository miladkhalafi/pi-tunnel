"""Key diagnostics for troubleshooting SSH authentication issues."""
import base64
import hashlib
from pathlib import Path

from models import get_authorized_keys_path, list_pis

# Key type prefixes (must match app.py PUBKEY_PREFIXES for parsing)
_KEY_PREFIXES = (
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
)


def fingerprint_from_public_key(key_str: str) -> str | None:
    """Compute SHA256 fingerprint from public key string (matches ssh-keygen -lf -E sha256)."""
    parts = key_str.strip().split(None, 2)
    if len(parts) < 2:
        return None
    try:
        raw = base64.b64decode(parts[1])
        digest = hashlib.sha256(raw).digest()
        b64 = base64.b64encode(digest).rstrip(b"=").decode()
        return "SHA256:" + ":".join(b64[i : i + 2] for i in range(0, len(b64), 2))
    except Exception:
        return None


def parse_authorized_keys_line(line: str) -> tuple[str, str] | None:
    """Extract (key_type, base64_part) from authorized_keys line. Handles options and comments."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    tokens = line.split()
    for i, tok in enumerate(tokens):
        if tok in _KEY_PREFIXES and i + 1 < len(tokens):
            base64_part = tokens[i + 1]
            if base64_part and all(
                c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
                for c in base64_part
            ):
                return (tok, base64_part)
    return None


def _read_authorized_keys_lines(path: Path) -> list[dict]:
    """Read authorized_keys and return list of {fingerprint, comment, key_line}."""
    lines = []
    if not path.exists():
        return lines
    try:
        content = path.read_text()
    except OSError:
        return lines
    for line in content.splitlines():
        parsed = parse_authorized_keys_line(line)
        if parsed:
            key_type, base64_part = parsed
            key_line = f"{key_type} {base64_part}"
            fp = fingerprint_from_public_key(key_line)
            comment = line.split()[-1] if len(line.split()) > 2 else ""
            lines.append({"fingerprint": fp, "comment": comment, "key_line": key_line})
    return lines


def run_diagnostics() -> dict:
    """Run key diagnostics. Returns authorized_keys status, per-Pi status, and sync status."""
    path = get_authorized_keys_path()
    ak_lines = _read_authorized_keys_lines(path)
    ak_fingerprints = {line["fingerprint"] for line in ak_lines if line["fingerprint"]}

    pis = list_pis()
    pi_results = []
    sync_ok = True

    for pi in pis:
        pk = (pi.get("public_key") or "").strip()
        fingerprint = fingerprint_from_public_key(pk) if pk else None
        in_ak = fingerprint in ak_fingerprints if fingerprint else False
        if pk and not in_ak:
            sync_ok = False
        status = "OK" if (pk and in_ak) else ("Missing" if pk else "Not registered")
        pi_results.append(
            {
                "id": pi["id"],
                "name": pi["name"],
                "port": pi["port"],
                "public_key_set": bool(pk),
                "fingerprint": fingerprint,
                "in_authorized_keys": in_ak,
                "status": status,
            }
        )

    return {
        "authorized_keys": {
            "path": str(path),
            "exists": path.exists(),
            "readable": path.exists() and path.is_file(),
            "line_count": len(ak_lines),
            "lines": [
                {
                    "fingerprint": line["fingerprint"],
                    "comment": line["comment"],
                    "in_db": any(
                        fingerprint_from_public_key(p.get("public_key") or "") == line["fingerprint"]
                        for p in pis
                        if p.get("public_key")
                    ),
                }
                for line in ak_lines
            ],
        },
        "pis": pi_results,
        "sync_ok": sync_ok,
    }


def check_key(public_key: str) -> dict:
    """Check if a pasted public key matches any Pi and/or is in authorized_keys."""
    pk = (public_key or "").strip()
    fingerprint = fingerprint_from_public_key(pk)
    if not fingerprint:
        return {"error": "Invalid public key format", "fingerprint": None}

    path = get_authorized_keys_path()
    ak_lines = _read_authorized_keys_lines(path)
    in_authorized_keys = any(line["fingerprint"] == fingerprint for line in ak_lines)

    matches_pi = None
    for pi in list_pis():
        pk = pi.get("public_key") or ""
        if pk and fingerprint_from_public_key(pk) == fingerprint:
            matches_pi = {"id": pi["id"], "name": pi["name"]}
            break

    return {
        "fingerprint": fingerprint,
        "matches_pi": matches_pi,
        "in_authorized_keys": in_authorized_keys,
    }
