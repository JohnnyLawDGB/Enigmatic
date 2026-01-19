# VPS Service (systemd)

This project ships a minimal HTTP API (`enigmatic-api`) that can run as a
systemd service on a VPS. The example below binds to localhost only and is
meant for private access (SSH tunnel, VPN, or a local reverse proxy).

## 1) Create the virtualenv

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 2) Create the unit file

Create `/etc/systemd/system/enigmatic-api.service`:

```ini
[Unit]
Description=Enigmatic HTTP API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/Enigmatic
Environment=ENIGMATIC_API_HOST=127.0.0.1
Environment=ENIGMATIC_API_PORT=8123
Environment=DGB_RPC_USER=rpcuser
Environment=DGB_RPC_PASSWORD=rpcpass
Environment=DGB_RPC_HOST=127.0.0.1
Environment=DGB_RPC_PORT=14022
Environment=DGB_RPC_WALLET=JohnnyTest
ExecStart=/home/YOUR_USER/Enigmatic/.venv/bin/enigmatic-api
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## 3) Enable + start

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now enigmatic-api
```

## 4) Logs

```bash
journalctl -u enigmatic-api -f
```

## Notes

- Keep the bind address on `127.0.0.1` and access via a tunnel.
- If you need multiple wallets, pass an `rpc` override per request (see
  `docs/API_CONTRACT.md`).
