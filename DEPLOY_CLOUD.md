# DentaCare — Cloud Node Deployment

The cloud node runs the **same `dental_clinic.py`** with `CLINIC_CLOUD_MODE=1`, which turns it into a **multi-tenant** server: a master registry DB (`cloud_master.db`) tracks clinics, and each clinic gets its own SQLite file (`clinic_<id>.db`). Every `/api/*` request must carry a clinic token (`X-Clinic-Token` header or `?clinic_token=`); a `before_request` hook resolves it and points the per-request DB path at that clinic's file, so the existing handlers run unchanged but see only that tenant's data.

The staff web portal is **not** served here — staff use their own local server. The cloud node is purely the rendezvous point for sync (and remote mobile clients later).

```
Internet ──HTTPS──▶ Caddy (auto Let's Encrypt) ──http──▶ app:5000  (Flask, CLINIC_CLOUD_MODE=1)
                                                              │
                                                        /data volume
                                                   ├── cloud_master.db   (clinics registry)
                                                   ├── clinic_1.db
                                                   ├── clinic_2.db
                                                   └── …
```

## Current deployment

| | |
|---|---|
| Server | DigitalOcean droplet `dentacare-cloud` — Frankfurt (fra1), Ubuntu 24.04, 2 GB / 1 vCPU / 50 GB |
| Public IP | `68.183.208.166` |
| Hostname | `app.dentacare.tech` (A record → the IP) |
| Firewall | `dentacare-fw` — inbound 22 / 80 / 443 only |
| App dir on server | `/opt/dentacare/` (repo files: `dental_clinic.py`, `requirements.txt`, `cloud/`) |
| Stack | `cloud/docker-compose.yml` — `app` (Flask) + `caddy` (TLS/reverse-proxy) |
| Data | Docker volume `dentacare-data` mounted at `/data` |

## First-time setup

On the droplet (`ssh root@68.183.208.166`):

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com | sh

# 2. Make the app dir
mkdir -p /opt/dentacare
```

From your workstation (the repo root), copy the needed files up — note: don't `git clone`, the repo isn't pushed and some assets are untracked:

```bash
scp dental_clinic.py requirements.txt root@68.183.208.166:/opt/dentacare/
scp -r cloud root@68.183.208.166:/opt/dentacare/
# optional logo asset (served by /logo, harmless if absent):
scp DentaCare.PNG root@68.183.208.166:/opt/dentacare/  2>/dev/null || true
```

Back on the droplet:

```bash
cd /opt/dentacare/cloud
# Set a real admin password for the master DB:
#   edit docker-compose.yml -> services.app.environment.CLINIC_ADMIN_PASSWORD
docker compose up -d --build
docker compose logs -f caddy        # watch for "certificate obtained" for app.dentacare.tech
```

Verify:

```bash
curl -s https://app.dentacare.tech/api/system/readiness
# register a clinic (returns clinic_id + clinic_token — store the token on that clinic's local server):
curl -s -X POST https://app.dentacare.tech/api/clinics/register \
  -H 'Content-Type: application/json' \
  -d '{"serial_number":"SERIAL-XXXX-0001","clinic_name":"Demo Clinic"}'
```

## Updating the app

```bash
# from your workstation:
scp dental_clinic.py root@68.183.208.166:/opt/dentacare/
# on the droplet:
cd /opt/dentacare/cloud && docker compose up -d --build app
```

The `/data` volume (clinic DBs + registry) persists across rebuilds.

## Environment / config

Set in `cloud/docker-compose.yml` (`services.app.environment`) or the `Dockerfile`:

| Var | Default (in image) | Notes |
|---|---|---|
| `CLINIC_CLOUD_MODE` | `1` | Multi-tenant routing on. |
| `CLINIC_DEBUG` | `0` | Production mode → served by waitress. |
| `CLINIC_HOST` / `CLINIC_PORT` | `0.0.0.0` / `5000` | Internal bind; Caddy is the public entrypoint. |
| `CLINIC_DATA_DIR` | `/data` | Where `cloud_master.db` and `clinic_<id>.db` live (the mounted volume). |
| `CLINIC_BACKUP_INTERVAL_HOURS` | `0` | The built-in backup thread is disabled on the cloud node (it would only cover `cloud_master.db`). Per-clinic off-server snapshots to DO Spaces are a later phase. |
| `CLINIC_ADMIN_PASSWORD` | `change-me-please` | Master-DB admin password — change it. |

The hostname for TLS lives in `cloud/Caddyfile` (`app.dentacare.tech`) — change it there if the domain changes, then `docker compose up -d caddy`.

## API surface on the cloud node

- `POST /api/clinics/register` — `{serial_number, clinic_name}` → `{clinic_id, clinic_token, already_registered}`. Idempotent per serial. **No token required.**
- `GET /api/system/readiness` — health check. No token required.
- Everything else under `/api/*` — requires a valid `X-Clinic-Token` (or `?clinic_token=`), routed to that clinic's DB. This includes `/api/sync/export`, `/api/sync/import`, `/api/patients`, etc.
- Non-`/api/` paths — return a short "use your local server" notice.
- `/api/medical-images*` — returns `501` on the cloud node (uploads aren't part of cloud sync and the folder isn't tenant-scoped).

## Known limitations (Phase 1)

- Serial validation is currently just **uniqueness** (one clinic per serial, ≥ 8 chars). HMAC-signed-serial gating (via `serial_generator.py`'s signing key) is a follow-up.
- No per-clinic cloud backups yet (see `CLINIC_BACKUP_INTERVAL_HOURS` above).
- No rate limiting on the public endpoints yet; the firewall + Caddy are the only front-line protection. (`/api/clinics/register` is the main thing to watch.)
- The cloud node currently shares one Flask session secret across all tenants (stored in `cloud_master.db`); the portal isn't reachable here so this is low-impact, but worth knowing.

## Teardown

```bash
# stop the stack (keeps data):
cd /opt/dentacare/cloud && docker compose down
# destroy the droplet entirely:
doctl compute droplet delete dentacare-cloud
```
