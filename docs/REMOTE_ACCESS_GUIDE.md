# Remote Access Guide (HighwayVLM)

This guide documents how to access HighwayVLM from your laptop when the server port is not directly reachable from your network.

## What We Solved

- Direct access to `http://cege-u-tol-gpu-02.cege.umn.edu:3000/incidents` timed out.
- SSH access to the server worked.
- The `highwayvlm` container was stopped and needed to be started.
- After the container was up, an SSH tunnel from local `localhost:3000` to remote `127.0.0.1:3000` made the app reachable.

## Prerequisites

- You can SSH into:
  - `yusuf369@cege-u-tol-gpu-02.cege.umn.edu`
- Docker is installed on the server (already true in this environment).
- You know your SSH key passphrase or server password.

## One-Time Notes

- If SSH asks to trust the host key the first time, type `yes` only if hostname/fingerprint is expected.
- When SSH asks for key passphrase, typing is hidden (no dots/stars). This is normal.

## Quick Start (Daily Workflow)

### 1) Start HighwayVLM on the server

Run from local PowerShell:

```powershell
ssh yusuf369@cege-u-tol-gpu-02.cege.umn.edu "docker start highwayvlm; docker ps --filter name=^highwayvlm$ --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
```

Expected result includes:

- `highwayvlm   Up ...`
- `0.0.0.0:3000->8000/tcp`

### 2) Open SSH tunnel (keep this terminal open)

```powershell
ssh -N -L 3000:127.0.0.1:3000 yusuf369@cege-u-tol-gpu-02.cege.umn.edu
```

No output is normal. It means tunnel is active.

### 3) Open the app in browser

```text
http://localhost:3000/incidents
```

### 4) Stop when done

- Go to the tunnel terminal.
- Press `Ctrl+C`.

## Verification Commands

Check server app health:

```powershell
ssh yusuf369@cege-u-tol-gpu-02.cege.umn.edu "curl -s http://127.0.0.1:3000/health; echo"
```

Expected:

```text
{"status":"ok"}
```

Check local tunnel health (while tunnel is open):

```powershell
curl http://localhost:3000/health
```

Expected:

```text
{"status":"ok"}
```

## Troubleshooting

### `Permission denied (publickey,password)`

Possible causes:

- Typo in SSH target (for example `user@@host`).
- Wrong username/password.
- Account requires key-based auth.

Fix:

- Use exact format: `ssh yusuf369@cege-u-tol-gpu-02.cege.umn.edu`

### `channel X: open failed: connect failed: Connection refused`

Meaning:

- Tunnel connected to SSH, but target port on server is not listening.

Fix:

- Ensure container is running:
  - `docker start highwayvlm`
- Confirm remote service:
  - `curl http://127.0.0.1:3000/health`

### Tunnel opens but browser shows wrong/random app

Meaning:

- You tunneled to the wrong remote port/service.

Fix:

- For HighwayVLM in this setup, use remote `127.0.0.1:3000`.
- Confirm with:
  - `docker ps` shows `highwayvlm` mapping `3000->8000`.

### `http://cege-u-tol-gpu-02...:3000` times out from laptop

Meaning:

- Direct campus/server firewall path is blocked externally.

Fix:

- Use SSH tunnel and access `http://localhost:3000/incidents` instead.

### `localhost:3000` blank or not loading

Possible causes:

- Tunnel process is not running.
- Old/conflicting SSH tunnel still attached.

Fix:

1. Close old tunnel windows (`Ctrl+C`).
2. Kill stale local SSH processes:

```powershell
Get-Process ssh -ErrorAction SilentlyContinue | Stop-Process -Force
```

3. Re-open tunnel:

```powershell
ssh -N -L 3000:127.0.0.1:3000 yusuf369@cege-u-tol-gpu-02.cege.umn.edu
```

## Useful Diagnostics

Show running containers:

```powershell
ssh yusuf369@cege-u-tol-gpu-02.cege.umn.edu "docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'"
```

Show recent HighwayVLM logs:

```powershell
ssh yusuf369@cege-u-tol-gpu-02.cege.umn.edu "docker logs --tail 120 highwayvlm"
```

