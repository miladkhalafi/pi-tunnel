import os
from functools import wraps
from flask import Flask, render_template, request, jsonify, Response

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


@app.before_request
def setup():
    init_db()


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


def get_base_url():
    """Base URL for registration links (SERVER_IP or request host)."""
    return os.environ.get("SERVER_URL", "").rstrip("/") or request.host_url.rstrip("/")


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


@app.route("/register/<token>/script")
def register_script(token):
    pi = get_pi_by_token(token)
    if not pi:
        return "Invalid or expired registration link.", 404
    base_url = get_base_url()
    return render_template("register_script.sh", token=token, base_url=base_url), 200, {
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
    app.run(host="0.0.0.0", port=8080)
