"""WebSocket + SSH bridge for web terminal."""
import json
import logging
import os
import threading
import paramiko
from flask import request
from flask_sock import Sock, ConnectionClosed

from models import get_pi_by_id
from terminal_auth import validate_token

logger = logging.getLogger(__name__)

SSH_HOST = os.environ.get("SSH_HOST", "pi-tunnel")
SSH_USERNAME = os.environ.get("SSH_USERNAME", "pi")
SSH_PRIVATE_KEY_PATH = os.environ.get("SSH_PRIVATE_KEY_PATH", "")


def run_terminal(ws, pi_id: int):
    """Handle WebSocket connection and bridge to SSH."""
    pi = get_pi_by_id(pi_id)
    if not pi:
        ws.send("Error: Pi not found")
        return
    if not pi.get("public_key"):
        ws.send("Error: Pi not registered yet")
        return

    key_path = SSH_PRIVATE_KEY_PATH.strip()
    if not key_path or not os.path.isfile(key_path):
        ws.send("Error: SSH private key not configured. Mount key and set SSH_PRIVATE_KEY_PATH.")
        return

    port = pi["port"]
    stop = threading.Event()

    try:
        client = paramiko.SSHClient()
        # WarningPolicy: log unknown host keys but allow connection (internal Docker network)
        # Prefer RejectPolicy + known_hosts volume for stricter environments
        client.set_missing_host_key_policy(paramiko.WarningPolicy())
        client.connect(
            SSH_HOST,
            port=port,
            username=SSH_USERNAME,
            key_filename=key_path,
            allow_agent=False,
            look_for_keys=False,
        )
        logger.info("SSH connected to %s:%s (pi_id=%s)", SSH_HOST, port, pi_id)
        channel = client.invoke_shell(term="xterm-256color", width=80, height=24)
        channel.settimeout(0.1)

        def read_ssh():
            try:
                while not stop.is_set():
                    if channel.recv_ready():
                        data = channel.recv(4096)
                        if data:
                            try:
                                ws.send(data.decode("utf-8", errors="replace"))
                            except ConnectionClosed:
                                break
                    else:
                        stop.wait(0.05)
            except (ConnectionClosed, OSError):
                pass
            finally:
                stop.set()

        def read_ws():
            try:
                while not stop.is_set():
                    data = ws.receive()
                    if data is None:
                        break
                    if isinstance(data, str):
                        try:
                            obj = json.loads(data)
                            if isinstance(obj, dict) and obj.get("resize"):
                                w, h = obj.get("cols", 80), obj.get("rows", 24)
                                channel.resize_pty(width=w, height=h)
                                continue
                        except json.JSONDecodeError:
                            pass
                        channel.send(data.encode("utf-8"))
                    elif isinstance(data, bytes):
                        channel.send(data)
            except (ConnectionClosed, OSError):
                pass
            finally:
                stop.set()
                try:
                    channel.close()
                except Exception:
                    pass
                try:
                    client.close()
                except Exception:
                    pass

        t = threading.Thread(target=read_ssh, daemon=True)
        t.start()
        read_ws()
        stop.set()
        t.join(timeout=1)
    except paramiko.SSHException as e:
        ws.send(f"Error: SSH connection failed: {e}")
    except Exception as e:
        ws.send(f"Error: {e}")


def register_terminal(sock: Sock):
    """Register WebSocket route with Flask-Sock."""
    @sock.route("/ws/terminal/<int:pi_id>")
    def terminal_ws(ws, pi_id):
        token = request.args.get("token", "")
        if not validate_token(token, pi_id):
            ws.send("Error: Invalid or expired token. Refresh the page.")
            return
        run_terminal(ws, pi_id)
