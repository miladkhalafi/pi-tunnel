# Pi Tunnel - Connection Error Troubleshooting

## Error: "Unable to connect to port 10022 on 172.18.0.x"

This means the **reverse tunnel from your Pi is not active**. Port 10022 (or your Pi's assigned port) only listens when the Pi has successfully connected and established its reverse SSH tunnel.

### 1. Run the full registration script ON the Raspberry Pi

You must run the registration script **on the Pi itself**, not just register the key via the web UI. The script does two things:
- Registers your Pi's public key with the server
- **Installs and starts the autossh tunnel service** (this is what makes port 10022 listen)

```bash
# On your Raspberry Pi, run:
curl -sSL https://YOUR-SERVER/register/YOUR_TOKEN/script | bash
```

Replace with your actual registration URL from the web UI (e.g. `https://dashboard.example.com/register/abc123.../script`).

### 2. Set WEB_URL or SERVER_URL on the server

The registration script needs `SERVER_HOST` to know where to connect. This is injected from `WEB_URL` or `SERVER_URL` in your `.env`:

```env
WEB_URL=https://your-actual-server.com
# or
SERVER_URL=https://your-actual-server.com
```

If these are unset, the script will prompt for the server hostname (only works when run interactively).

### 3. Ensure the Pi can reach the server on port 2222

- The Pi connects to your server on **port 2222** (SSH)
- Check firewall: port 2222 must be open on the server
- If using a reverse proxy, ensure it forwards TCP (not just HTTP) to port 2222, or expose 2222 directly

### 4. Check the tunnel service on the Pi

After running the registration script:

```bash
# On the Pi:
sudo systemctl status ssh-reverse-tunnel.service
```

- **Active (running)** = tunnel is up; wait a few seconds and try the web terminal again
- **Failed** = check logs: `journalctl -u ssh-reverse-tunnel.service -n 50`

Common failures:
- **Connection refused** → Pi can't reach server (firewall, wrong host)
- **Permission denied** → Pi's key not in server's authorized_keys (re-run registration)
- **Host key verification failed** → Add server to known_hosts or use `-o StrictHostKeyChecking=no` (autossh handles this)

### 5. Username mismatch (Raspberry Pi OS Bookworm+)

Newer Raspberry Pi OS uses your created username instead of `pi`. If your Pi user is different (e.g. `milad`), set in `.env`:

```env
SSH_USERNAME=milad
```

Then restart the pi-tunnel-web container.

### 6. Verify port is listening (on the server)

When the tunnel is active, you can check:

```bash
# From the host running Docker:
docker exec pi-tunnel nc -z localhost 10022 && echo "Port 10022 is listening" || echo "Port 10022 is NOT listening"
```

If it says "NOT listening", the Pi's tunnel is not connected.

---

## Error: "kex_exchange_identification" (SSH key exchange failed)

This error occurs when an SSH connection is closed during the initial key exchange phase—before authentication. The client expects an SSH protocol banner but receives something else (or the connection drops).

### 1. Wrong port / reverse proxy

If port 2222 or 10022–10031 is behind nginx, HAProxy, or another reverse proxy, ensure **TCP passthrough** (stream), not HTTP. SSH expects raw TCP; an HTTP response (e.g. "400 Bad Request") causes this error.

- Expose port 2222 directly, or use TCP stream forwarding
- Do not route SSH through an HTTP/HTTPS proxy

### 2. MaxStartups limit

If many Pis connect or autossh reconnects frequently, sshd may drop connections. The pi-tunnel-sshd image includes `MaxStartups 30:100:60` to allow more concurrent unauthenticated connections. If you use a custom sshd_config, ensure it has a sufficient value.

### 3. Tunnel stability

On the Pi, check if the tunnel keeps reconnecting:

```bash
journalctl -u ssh-reverse-tunnel -n 50
```

If the tunnel is flapping, investigate network issues, firewall, or packet loss between the Pi and server.

### 4. Firewall

Ensure ports 2222 and 10022–10031 are open on the server and not rate-limited by a firewall or security group.

### Quick diagnostic commands

```bash
# On Pi: check tunnel stability
journalctl -u ssh-reverse-tunnel -n 50

# On server: verify sshd is listening
docker exec pi-tunnel nc -z localhost 22 && echo "sshd OK"

# Test raw SSH (bypass web terminal)
ssh -v -p 10022 pi@localhost   # from host; replace port with Pi's assigned port
```

Verbose SSH output (`-v`) will show whether the banner is HTTP (wrong proxy) or SSH (correct path).
