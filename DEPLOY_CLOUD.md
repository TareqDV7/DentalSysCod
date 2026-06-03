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
docker compose up -d --build
docker compose logs -f caddy        # watch for "certificate obtained" for app.dentacare.tech
```

The cloud node does not seed a staff admin login — its only public surface is `/api/*` (token-authenticated), so there is no admin password to configure.

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
| `CLINIC_BACKUP_INTERVAL_HOURS` | `6` | The cloud-aware backup thread snapshots `cloud_master.db` and every `clinic_<id>.db` in `/data` into `/data/backups/<label>/<label>_<ts>.db` every N hours. Set `0` to disable. |
| `CLINIC_BACKUP_RETENTION` | `20` | Most recent N snapshots kept per tenant subfolder; older ones are pruned. |
| `CLINIC_REGISTER_RATE_LIMIT` | `10` | Max successful + failed `/api/clinics/register` attempts per source IP within the rate window. Set `0` to disable. |
| `CLINIC_REGISTER_RATE_WINDOW` | `3600` | Rate-limit window for the above, in seconds. |
| `CLINIC_SERIAL_SIGNING_KEY` | _(unset)_ | Base64-encoded HMAC key matching the one used by `serial_generator.py`. When set, registration verifies an `offline_token` if the client sends one. |
| `CLINIC_REQUIRE_SIGNED_SERIAL` | `0` | If `1`, **rejects** registration unless a valid `offline_token` (signed by the key above) is provided. Default off so existing demo serials keep registering during rollout. |

> The cloud node intentionally does **not** seed a staff admin user — the staff portal isn't served here, so `CLINIC_ADMIN_PASSWORD` is unused in `CLINIC_CLOUD_MODE=1`.

The hostname for TLS lives in `cloud/Caddyfile` (`app.dentacare.tech`) — change it there if the domain changes, then `docker compose up -d caddy`.

## Enabling signed-serial enforcement

By default `/api/clinics/register` accepts any unique serial (≥ 8 chars). To require that every registering clinic present an HMAC-signed `offline_token` (issued by `serial_generator.py`), roll out in two stages so nothing breaks mid-flight.

**Prerequisite — both the desktop *and* mobile clients must forward a signed token first.** The cloud only checks what it receives; a local server pairs via `POST /api/cloud/pair`, which forwards the `offline_token` it resolves in this order: the pair request body → `app_settings['cloud_offline_token']` → env `CLINIC_OFFLINE_TOKEN`. **Do not set `CLINIC_REQUIRE_SIGNED_SERIAL=1` until every local server (and any mobile client that registers directly) is configured with its signed token** — otherwise their pairing will be rejected with `403`.

1. **Generate the signing key** (once, kept secret — this is what `serial_generator.py` signs with):

   ```bash
   openssl rand -base64 32        # → put the output in CLINIC_SERIAL_SIGNING_KEY
   ```

   Store it in `cloud/.env` on the droplet (gitignored, `chmod 600`) — **never** commit it or paste it into `docker-compose.yml`:

   ```bash
   # cloud/.env
   CLINIC_SERIAL_SIGNING_KEY=<the base64 string above>
   CLINIC_REQUIRE_SIGNED_SERIAL=0      # stage 1: verify-if-present, don't reject yet
   ```

2. **Issue signed tokens** for each clinic with the matching key, and load the token onto each local server:

   ```bash
   # backend_key.json holds {"key": "<same base64 string>"}
   python serial_generator.py --clinic "Smile Dental" --code "SMD" \
     --device "SERVER-ID" --key-file backend_key.json
   # → copy the "Offline License Token" line; on the clinic's local server, pass it
   #   in the /api/cloud/pair body as offline_token, OR set env CLINIC_OFFLINE_TOKEN.
   ```

   The token's `payload.serial` must equal the `serial_number` the clinic registers with, and its `grace_until` must be in the future.

3. **Soft-launch (stage 1):** `docker compose up -d --build app` with `CLINIC_REQUIRE_SIGNED_SERIAL=0`. Now every register call that *includes* a token is verified (bad signatures / wrong serial / expired tokens are rejected), but tokenless legacy registrations still succeed. Watch the logs and confirm all live clients are sending valid tokens.

4. **Enforce (stage 2):** once all clients forward a valid token, set `CLINIC_REQUIRE_SIGNED_SERIAL=1` in `cloud/.env` and `docker compose up -d app`. Registrations without a valid signed token now get `403`. If the key is somehow missing while `REQUIRE=1`, register returns `500` ("Server signing key not configured") rather than silently allowing anyone in.

To roll back, set `CLINIC_REQUIRE_SIGNED_SERIAL=0` (or unset `CLINIC_SERIAL_SIGNING_KEY` to disable the gate entirely) and redeploy `app`.

## API surface on the cloud node

- `POST /api/clinics/register` — `{serial_number, clinic_name, offline_token?}` → `{clinic_id, clinic_token, already_registered}`. Idempotent per serial. **No clinic token required.** `offline_token` is the HMAC-signed token from `serial_generator.py`; required when `CLINIC_REQUIRE_SIGNED_SERIAL=1`, otherwise optional but verified when present. Local servers don't call this directly — they call their own `POST /api/cloud/pair`, which forwards the `offline_token` (from the pair body, `app_settings['cloud_offline_token']`, or env `CLINIC_OFFLINE_TOKEN`). See *Enabling signed-serial enforcement*.
- `GET /api/system/readiness` — health check. No token required.
- Everything else under `/api/*` — requires a valid `X-Clinic-Token` (or `?clinic_token=`), routed to that clinic's DB. This includes `/api/sync/export`, `/api/sync/import`, `/api/patients`, etc.
- Non-`/api/` paths — return a short "use your local server" notice.
- `/api/medical-images*` — returns `501` on the cloud node (uploads aren't part of cloud sync and the folder isn't tenant-scoped).

## Backups on the cloud node

The same backup thread the local server uses runs here too, but cloud-aware: every `CLINIC_BACKUP_INTERVAL_HOURS` it snapshots `cloud_master.db` plus every `clinic_<id>.db` it finds in `/data`, into per-tenant subfolders:

```
/data/backups/
├── master/master_YYYYMMDD_HHMMSS.db
├── clinic_1/clinic_1_YYYYMMDD_HHMMSS.db
├── clinic_2/clinic_2_YYYYMMDD_HHMMSS.db
└── …
```

Each subfolder is pruned to the most recent `CLINIC_BACKUP_RETENTION` files independently. At the defaults (6h / 20) that's ~5 days of recovery per tenant. One tenant's failure (e.g. corrupt file, permission error) is logged and skipped — it never aborts the other tenants' snapshots, and the stub destination file is cleaned up. Snapshots use SQLite's online backup API, so they're consistent without stopping the server.

**Restore** — copy the desired snapshot over the matching DB file inside the `dentacare-data` volume and restart the stack:

```bash
ssh root@68.183.208.166
# inspect / pick a snapshot
docker run --rm -v dentacare-data:/data alpine ls /data/backups/clinic_1/
# restore (example)
docker run --rm -v dentacare-data:/data alpine sh -c \
  'cp /data/backups/clinic_1/clinic_1_20260514_120000.db /data/clinic_1.db'
cd /opt/dentacare/cloud && docker compose restart app
```

Snapshots stay on the droplet — for true off-server durability (so a droplet loss doesn't take backups with it), pull a copy to your workstation periodically, or enable DigitalOcean snapshots on the droplet, or add Spaces-upload in a follow-up phase.

## Known limitations (Phase 1)

- Serial validation defaults to **uniqueness** (one clinic per serial, ≥ 8 chars). HMAC-signed-serial gating is available and wired end-to-end (`/api/cloud/pair` forwards the token) — enable it per *Enabling signed-serial enforcement*. Default stays off.
- `/api/clinics/register` is rate-limited per source IP (default 10/hour) and can be gated on HMAC-signed `offline_token`s via the two `CLINIC_SERIAL_SIGNING_KEY` / `CLINIC_REQUIRE_SIGNED_SERIAL` envs above (issued by `serial_generator.py --key-file …`). The rate limiter is **in-process only** — it resets on restart and is not shared across replicas; behind a single Caddy + single app container that's adequate, but a horizontally-scaled deployment would need a shared store (e.g. Redis). Other public endpoints are not rate-limited yet.
- Backups are written to the same droplet volume as the live data (see *Backups* above). Off-server durability (DO Spaces upload) is a planned follow-up.
- The cloud node currently shares one Flask session secret across all tenants (stored in `cloud_master.db`); the portal isn't reachable here so this is low-impact, but worth knowing.

## Teardown

```bash
# stop the stack (keeps data):
cd /opt/dentacare/cloud && docker compose down
# destroy the droplet entirely:
doctl compute droplet delete dentacare-cloud
```
