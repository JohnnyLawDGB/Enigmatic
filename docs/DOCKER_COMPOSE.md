# Docker Compose Notes

Use `docker-compose.yml` for a simple local deployment of `enigmatic-api`.

## Quick start

```bash
cp .env.example .env
docker compose up --build -d
```

The service binds to `127.0.0.1:8123` by default (not internet-facing).

## DigiByte RPC on the host

Inside a container, `127.0.0.1` refers to the container itself. If your
DigiByte node runs on the host:

1. Uncomment the `extra_hosts` block in `docker-compose.yml`.
2. Set `DGB_RPC_HOST=host.docker.internal` in `.env`.

On Linux, Docker uses `host-gateway` to resolve `host.docker.internal`.

## DigiByte RPC in another container

If your node runs in another container on the same compose network, set
`DGB_RPC_HOST` to that service name.
