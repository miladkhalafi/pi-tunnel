import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from contextlib import contextmanager

from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "pi_tunnel.db"
AUTHORIZED_KEYS_PATH = Path(__file__).parent / "authorized_keys"


def get_db_path():
    return Path(os.environ.get("DB_PATH", DB_PATH))


def get_authorized_keys_path():
    return Path(os.environ.get("AUTHORIZED_KEYS_PATH", AUTHORIZED_KEYS_PATH))


def get_port_range():
    """Return (start, end) for tunnel port range. Default 10022-10031."""
    start = int(os.environ.get("PORT_START", "10022"))
    count = int(os.environ.get("PORT_COUNT", "10"))
    return start, start + count


@contextmanager
def get_db():
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                port INTEGER NOT NULL,
                public_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'viewer')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _bootstrap_admin(conn)


def _bootstrap_admin(conn: sqlite3.Connection):
    """Create first admin from ADMIN_USERNAME/ADMIN_PASSWORD if users table is empty."""
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count > 0:
        return
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not username or not password:
        return
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password, method="scrypt"), "admin"),
        )
        logger.info("Bootstrap: created admin user %r from ADMIN_USERNAME/ADMIN_PASSWORD", username)
    except sqlite3.IntegrityError:
        pass


def create_user(username: str, password: str, role: str) -> dict:
    """Create a new user. Role must be 'admin' or 'viewer'."""
    if role not in ("admin", "viewer"):
        raise ValueError("role must be 'admin' or 'viewer'")
    username = username.strip()
    if not username:
        raise ValueError("username required")
    if not password:
        raise ValueError("password required")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password, method="scrypt"), role),
        )
        row = conn.execute(
            "SELECT id, username, role, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row)


def get_user_by_username(username: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, role, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def verify_user(username: str, password: str) -> dict | None:
    """Verify credentials and return user dict (without password_hash) if valid."""
    user = get_user_by_username(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return None
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


def has_any_users() -> bool:
    with get_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0


def list_users() -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY username"
        ).fetchall()
        return [dict(r) for r in rows]


def delete_user(user_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return cur.rowcount > 0


def create_pi(name: str) -> dict:
    """Create a new Pi record, assign next available port. Returns pi dict."""
    port_start, port_end = get_port_range()
    with get_db() as conn:
        used_ports = {r["port"] for r in conn.execute("SELECT port FROM pis").fetchall()}
        available = [p for p in range(port_start, port_end) if p not in used_ports]
        if not available:
            raise ValueError(f"No ports available ({port_start}-{port_end - 1})")
        port = min(available)
        token = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO pis (name, token, port) VALUES (?, ?, ?)",
            (name, token, port)
        )
        row = conn.execute(
            "SELECT id, name, token, port, public_key, created_at FROM pis WHERE token = ?",
            (token,)
        ).fetchone()
        return dict(row)


def list_pis() -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, token, port, public_key, created_at FROM pis ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]


def get_pi_by_token(token: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name, token, port, public_key, created_at FROM pis WHERE token = ?",
            (token,)
        ).fetchone()
        return dict(row) if row else None


def get_pi_by_id(pi_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name, token, port, public_key, created_at FROM pis WHERE id = ?",
            (pi_id,)
        ).fetchone()
        return dict(row) if row else None


def register_public_key(token: str, public_key: str) -> bool:
    """Store public key for Pi and update authorized_keys file. Allows re-registration to update key."""
    pi = get_pi_by_token(token)
    if not pi:
        return False
    with get_db() as conn:
        conn.execute(
            "UPDATE pis SET public_key = ? WHERE token = ?",
            (public_key, token)
        )
    sync_authorized_keys()
    return True


def unregister_public_key(token: str, public_key: str) -> bool:
    """Clear public key for Pi if it matches. Used by uninstall script."""
    pi = get_pi_by_token(token)
    if not pi or not pi.get("public_key"):
        return False
    if pi["public_key"].strip() != public_key.strip():
        return False
    with get_db() as conn:
        conn.execute(
            "UPDATE pis SET public_key = NULL WHERE token = ?",
            (token,)
        )
    sync_authorized_keys()
    return True


def delete_pi(pi_id: int) -> bool:
    pi = get_pi_by_id(pi_id)
    if not pi:
        return False
    with get_db() as conn:
        conn.execute("DELETE FROM pis WHERE id = ?", (pi_id,))
    sync_authorized_keys()
    return True


def sync_authorized_keys():
    """Rewrite authorized_keys from all registered Pis."""
    path = get_authorized_keys_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    pis = list_pis()
    lines = []
    for pi in pis:
        if pi["public_key"]:
            # Format: key comment (pi name for clarity)
            # Sanitize name: newlines would corrupt authorized_keys format
            safe_name = (pi["name"] or "").replace("\n", "").replace("\r", "").strip() or "pi"
            lines.append(f"{pi['public_key'].strip()} pi-{safe_name}\n")
    path.write_text("".join(lines) if lines else "")


def get_setting(key: str) -> str | None:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_setting(key: str, value: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
