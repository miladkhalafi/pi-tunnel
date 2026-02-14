# Pi Remote Access

Control one or more Raspberry Pis remotely via reverse SSH tunnels. The Pi connects out to your server (works behind NAT); you SSH to the server, then connect to any Pi through the tunnel.

## How It Works

- **Raspberry Pi** (behind NAT): Opens an outbound SSH tunnel to your server. No port forwarding on your router.
- **Server** (static IP): Accepts tunnels and forwards them. You SSH to the server, then `ssh -p PORT user@localhost` to reach a Pi.
- **Web UI**: Create Pis, get unique registration URLs, and run a script on each Pi to generate keys and configure the tunnel automatically.

## Prerequisites

- A server with a static IP (or hostname)
- Raspberry Pi(s) with internet access
- Docker and Docker Compose on the server

## Quick Start

### 1. Deploy on Your Server

```bash
git clone https://github.com/YOUR_ORG/pi-remote-access.git
cd pi-remote-access
```

Create a `.env` file:

```bash
# Base URL for registration links (use your server's public URL)
SERVER_URL=https://your-server.com

# Optional: use pre-built images from GHCR
# IMAGE=ghcr.io/YOUR_ORG/pi-tunnel-sshd:latest
# WEB_IMAGE=ghcr.io/YOUR_ORG/pi-tunnel-web:latest

# Required for production
SECRET_KEY=your-random-secret-key

# Admin login (HTTP Basic Auth) - when set, dashboard requires login
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
```

Start the services:

```bash
docker compose up -d
```

This runs:
- **pi-tunnel-web** on port 8080 (web UI)
- **pi-tunnel** on port 2222 (SSH for Pi connections) and ports 10022–10031 (tunnel endpoints)

### 2. Configure the Web UI

1. Open `http://YOUR_SERVER:8080` (or your domain with reverse proxy).
2. In **Settings**, paste your server's SSH public key. This is the key you use when SSHing from the server to the Pi. If you don't have one:
   ```bash
   ssh-keygen -t ed25519 -N '' -f ~/.ssh/pi_shell_key
   cat ~/.ssh/pi_shell_key.pub
   ```
3. Click **Save**.

### 3. Add a Raspberry Pi

1. In the web UI, enter a name (e.g. `pi-home`) and click **Create**.
2. Copy the registration URL (e.g. `https://your-server.com/register/abc123...`).

### 4. Register the Pi (Headless)

On the Raspberry Pi, run:

```bash
curl -sSL https://your-server.com/register/YOUR_TOKEN/script | bash
```

The script will:
- Generate an SSH key if needed
- Send the public key to the server
- Add the server's public key to the Pi's `authorized_keys`
- Install autossh and create a systemd service for the tunnel

You'll be prompted for:
- **Server IP or hostname**: Your server's address
- **SSH port**: 2222 (default)

### 5. Connect to the Pi

1. SSH to your server.
2. Run:

```bash
ssh -p 10022 pi@localhost
```

Use the port shown in the web UI for that Pi. Replace `pi` with the username on the Pi if different.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVER_URL` | Base URL for registration links (e.g. `https://your-server.com`) | Request host |
| `SECRET_KEY` | Flask secret key (set in production) | `change-me-in-production` |
| `ADMIN_USERNAME` | Admin login (HTTP Basic Auth). When set with `ADMIN_PASSWORD`, dashboard requires login | (none) |
| `ADMIN_PASSWORD` | Admin password. Set with `ADMIN_USERNAME` to enable auth | (none) |
| `IMAGE` | pi-tunnel-sshd Docker image | `ghcr.io/your-org/pi-tunnel-sshd:latest` |
| `WEB_IMAGE` | pi-tunnel-web Docker image | `ghcr.io/your-org/pi-tunnel-web:latest` |

## Ports

| Port | Service |
|------|---------|
| 8080 | Web UI |
| 2222 | SSH (Pi connects here) |
| 10022–10031 | Tunnel endpoints (one per Pi) |

## Building from Source

```bash
# Build both images
docker compose build

# Or build individually
docker build -t pi-tunnel-sshd ./pi-tunnel-sshd
docker build -t pi-tunnel-web ./pi-tunnel-web
```

## GitHub Actions

On push to `main`, the workflow builds and pushes both images to GitHub Container Registry:

- `ghcr.io/<owner>/pi-tunnel-sshd:latest`
- `ghcr.io/<owner>/pi-tunnel-web:latest`

## Security Notes

- Use SSH keys only; password auth is disabled
- Set `SECRET_KEY` in production
- Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` to protect the dashboard
- Use HTTPS for the web UI (reverse proxy with nginx/Caddy)
- The registration token is the secret; anyone with the URL can register a Pi. Use a private network or restrict access to the web UI

## Troubleshooting

**Pi shows "Pending" after running the script**
- Ensure the server's public key is set in Settings
- Check that the Pi can reach the server (curl the registration URL)

**Cannot connect to Pi from server**
- Verify the tunnel is running: `systemctl status ssh-reverse-tunnel` on the Pi
- Check the port in the web UI matches the Pi's assigned port
- Ensure you're using the correct username (default: `pi`)

**Tunnel drops**
- autossh and systemd restart it automatically
- Check `journalctl -u ssh-reverse-tunnel -f` on the Pi for errors
