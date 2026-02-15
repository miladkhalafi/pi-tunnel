import os
import time
from collections import defaultdict
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

import paramiko
from flask import Flask, render_template, request, jsonify, Response
from flask_sock import Sock

from models import (
    init_db,
    create_pi,
    list_pis,
    get_pi_by_token,
    get_pi_by_id,
    register_public_key,
    delete_pi,
    get_setting,
    set_setting,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.config["SOCK_SERVER_OPTIONS"] = {"ping_interval": 25}
sock = Sock(app)

from terminal import register_terminal
register_terminal(sock)


def derive_public_key_from_private(path: str) -> str | None:
    """Load private key and return OpenSSH-format public key string."""
    try:
        key = paramiko.PKey.from_path(path)
        return f"{key.get_name()} {key.get_base64()}"
    except Exception:
        return None


def ensure_server_public_key():
    """Auto-populate server_public_key from env, file, or private key if not set."""
    if get_setting("server_public_key"):
        return
    key = os.environ.get("SERVER_PUBLIC_KEY", "").strip()
    if key:
        set_setting("server_public_key", key)
        return
    path = os.environ.get("SERVER_PUBLIC_KEY_PATH", "").strip()
    if path and Path(path).is_file():
        try:
            key = Path(path).read_text().strip()
            if key:
                set_setting("server_public_key", key)
                return
        except OSError:
            pass
    private_path = os.environ.get("SSH_PRIVATE_KEY_PATH", "/app/.ssh/id_ed25519").strip()
    if private_path and Path(private_path).is_file():
        key = derive_public_key_from_private(private_path)
        if key:
            set_setting("server_public_key", key)


@app.before_request
def setup():
    init_db()
    ensure_server_public_key()


def requires_auth(f):
    """Require HTTP Basic Auth when ADMIN_USERNAME and ADMIN_PASSWORD are set."""
    @wraps(f)
    def decorated(*args, **kwargs):
        username = os.environ.get("ADMIN_USERNAME")
        password = os.environ.get("ADMIN_PASSWORD")
        if username and password:
            auth = request.authorization
            if not auth or auth.username != username or auth.password != password:
                return Response(
                    "Authentication required",
                    401,
                    {"WWW-Authenticate": 'Basic realm="Pi Tunnel Admin"'},
                )
        return f(*args, **kwargs)
    return decorated


# In-memory rate limit for registration endpoint (per IP, 10/min)
_register_attempts = defaultdict(list)
REGISTER_RATE_LIMIT = 10
REGISTER_RATE_WINDOW = 60  # seconds


def rate_limit_register(f):
    """Limit registration POST attempts per IP to prevent brute-force token guessing."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method != "POST":
            return f(*args, **kwargs)
        ip = request.remote_addr or "unknown"
        now = time.time()
        # Prune old entries
        _register_attempts[ip] = [t for t in _register_attempts[ip] if now - t < REGISTER_RATE_WINDOW]
        if len(_register_attempts[ip]) >= REGISTER_RATE_LIMIT:
            return jsonify({"error": "Too many registration attempts. Try again later."}), 429
        _register_attempts[ip].append(now)
        return f(*args, **kwargs)
    return decorated


@app.route("/health")
def health():
    """Lightweight health check for Docker/orchestration."""
    return "", 200


def get_base_url():
    """Base URL for registration links (SERVER_URL or request host)."""
    return os.environ.get("SERVER_URL", "").rstrip("/") or request.host_url.rstrip("/")


def get_server_host():
    """Extract host (domain or IP) from base URL for tunnel connection."""
    base = get_base_url()
    if not base:
        return ""
    parsed = urlparse(base)
    return parsed.hostname or ""


@app.route("/")
@requires_auth
def index():
    pis = list_pis()
    server_public_key = get_setting("server_public_key")
    return render_template("index.html", pis=pis, base_url=get_base_url(), server_public_key=server_public_key)


@app.route("/api/pis", methods=["GET"])
@requires_auth
def api_list_pis():
    return jsonify(list_pis())


@app.route("/api/pis", methods=["POST"])
@requires_auth
def api_create_pi():
    data = request.get_json() or {}
    name = data.get("name", "pi").strip() or "pi"
    try:
        pi = create_pi(name)
        pi["registration_url"] = f"{get_base_url()}/register/{pi['token']}"
        return jsonify(pi), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/pis/<int:pi_id>", methods=["DELETE"])
@requires_auth
def api_delete_pi(pi_id):
    if delete_pi(pi_id):
        return "", 204
    return jsonify({"error": "Not found"}), 404


from terminal_auth import create_token


@app.route("/terminal/<int:pi_id>")
@requires_auth
def terminal_page(pi_id):
    pi = get_pi_by_id(pi_id)
    if not pi:
        return "Pi not found", 404
    token = create_token(pi_id)
    return render_template("terminal.html", pi=pi, token=token)


@app.route("/api/terminal-token/<int:pi_id>")
@requires_auth
def api_terminal_token(pi_id):
    """Return a fresh WebSocket token for reconnection."""
    pi = get_pi_by_id(pi_id)
    if not pi:
        return jsonify({"error": "Not found"}), 404
    token = create_token(pi_id)
    return jsonify({"token": token})


@app.route("/api/settings", methods=["POST"])
@requires_auth
def api_save_settings():
    data = request.get_json() or {}
    if "server_public_key" in data:
        set_setting("server_public_key", data["server_public_key"].strip())
    return jsonify({"ok": True})


@app.route("/register/<token>")
def register_page(token):
    pi = get_pi_by_token(token)
    if not pi:
        return "Invalid or expired registration link.", 404
    base_url = get_base_url()
    script_url = f"{base_url}/register/{token}/script"
    return render_template("register.html", pi=pi, script_url=script_url, base_url=base_url)


def get_server_ssh_port():
    """SSH port on server for Pi tunnel connections (default 2222)."""
    return int(os.environ.get("SSH_SERVER_PORT", "2222"))


@app.route("/register/<token>/script")
def register_script(token):
    pi = get_pi_by_token(token)
    if not pi:
        return "Invalid or expired registration link.", 404
    base_url = get_base_url()
    server_host = get_server_host()
    server_ssh_port = get_server_ssh_port()
    return render_template("register_script.sh", token=token, base_url=base_url, server_host=server_host, server_ssh_port=server_ssh_port), 200, {
        "Content-Type": "text/plain",
        "Content-Disposition": "inline",
    }


@app.route("/register/<token>/server-key")
def register_server_key(token):
    pi = get_pi_by_token(token)
    if not pi:
        return "Invalid or expired registration link.", 404
    key = get_setting("server_public_key")
    if not key:
        return "Server public key not configured.", 503
    return key.strip(), 200, {"Content-Type": "text/plain"}


@app.route("/register/<token>", methods=["POST"])
@rate_limit_register
def register_submit(token):
    pi = get_pi_by_token(token)
    if not pi:
        return jsonify({"error": "Invalid token"}), 404
    data = request.get_json()
    if not data or "public_key" not in data:
        return jsonify({"error": "public_key required"}), 400
    public_key = data["public_key"].strip()
    if not public_key or not public_key.startswith(("ssh-ed25519 ", "ssh-rsa ")):
        return jsonify({"error": "Invalid public key format"}), 400
    if register_public_key(token, public_key):
        return jsonify({"ok": True, "port": pi["port"]})
    return jsonify({"error": "Registration failed"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
