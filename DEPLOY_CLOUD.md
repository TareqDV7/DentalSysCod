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

## Backups & restore (standalone `backup` sidecar)

In addition to the in-process backup thread above, the stack ships a **dedicated `backup` service** (`cloud/backup.py`, stdlib-only). It runs in its own container so a problem in `app` can't take backups down with it, and — critically — it mounts the live data volume **read-only** and writes snapshots to a **separate** `dentacare-backups` volume. That isolation is the whole point: the live data path and the backup path don't share a writer.

**What it does** — every `BACKUP_INTERVAL_HOURS` (default 24h) it discovers every `*.db` directly under `/data` (`cloud_master.db` plus each `clinic_<id>.db`) and snapshots each one with SQLite's **online backup API** (never a raw file copy — that avoids torn writes / WAL inconsistencies on a live DB). Each run writes into a fresh timestamped directory, and snapshots are gzipped by default:

```
/backups/                          (the dentacare-backups volume)
├── 2026-06-02T03-00-00Z/
│   ├── cloud_master.db.gz
│   ├── clinic_1.db.gz
│   └── clinic_2.db.gz
├── 2026-06-03T03-00-00Z/
│   └── …
└── …
```

A single corrupt/locked tenant DB is logged and skipped — it never aborts the rest of the run. If *every* DB in a run fails (or the data dir is missing) the container exits non-zero so Docker's `restart: unless-stopped` retries.

**Retention / rotation** — after each run it prunes whole snapshot directories: any dir older than `BACKUP_RETENTION_DAYS` (default 14) is deleted, **except** the most-recent `BACKUP_MIN_KEEP` (default 7) directories, which are always kept regardless of age. So a clinic that goes quiet for a month still retains its last 7 snapshots. At the defaults that's at least 14 days *and* at least 7 runs of recovery history. Foreign directories (anything not in the `YYYY-MM-DDTHH-MM-SSZ` format the script writes) are never touched.

**Config** (set in `cloud/docker-compose.yml` `services.backup.environment`, or via `cloud/.env`):

| Var | Default | Notes |
|---|---|---|
| `CLINIC_DATA_DIR` | `/data` | Source dir (mounted read-only). |
| `BACKUP_DIR` | `/backups` | Destination (the `dentacare-backups` volume). |
| `BACKUP_RETENTION_DAYS` | `14` | Prune snapshot dirs older than this. |
| `BACKUP_MIN_KEEP` | `7` | Always keep at least this many newest, regardless of age. |
| `BACKUP_INTERVAL_HOURS` | `24` | Sleep between runs in `--loop` mode. |
| `BACKUP_GZIP` | `1` | Gzip each snapshot. Set `0` to store plain `.db`. |

**Pulling a backup off the droplet** — inspect the volume and copy a snapshot dir to your workstation:

```bash
ssh root@68.183.208.166
# list snapshot dirs
docker run --rm -v dentacare-backups:/backups alpine ls /backups
# copy one snapshot dir into a host folder, then scp it home
docker run --rm -v dentacare-backups:/backups -v /root/pull:/out \
  alpine cp -r /backups/2026-06-03T03-00-00Z /out/
# from your workstation:
scp -r root@68.183.208.166:/root/pull/2026-06-03T03-00-00Z ./
```

**Step-by-step restore** — replace a tenant's live DB with a snapshot, then restart the app:

```bash
ssh root@68.183.208.166
cd /opt/dentacare/cloud

# 1. Stop the app so nothing is writing the live DB during the swap.
docker compose stop app backup

# 2. Pick the snapshot you want to restore from.
docker run --rm -v dentacare-backups:/backups alpine ls /backups
#    e.g. 2026-06-03T03-00-00Z/clinic_1.db.gz

# 3. Decompress the snapshot and write it over the live file in dentacare-data.
#    (Mount both volumes; gunzip from /backups onto /data.)
docker run --rm \
  -v dentacare-backups:/backups:ro -v dentacare-data:/data \
  alpine sh -c \
  'gunzip -c /backups/2026-06-03T03-00-00Z/clinic_1.db.gz > /data/clinic_1.db'
#    For a non-gzipped snapshot (BACKUP_GZIP=0), use cp instead of gunzip:
#    cp /backups/<dir>/clinic_1.db /data/clinic_1.db

# 4. Bring the stack back up.
docker compose up -d app backup
docker compose logs -f app
```

Restoring `cloud_master.db` follows the same steps (swap `clinic_1.db` for `cloud_master.db`) — but be aware that rewinds the *registry* of clinics, so only do it if the registry itself was lost/corrupted.

**Offsite copy (recommended follow-up)** — these snapshots still live on the same droplet, so a droplet loss takes them too. The local rotating snapshots delivered here are the baseline; for true off-server durability, add a periodic push of the `dentacare-backups` volume to object storage (e.g. `rclone`/`aws s3 sync` to S3 or DigitalOcean Spaces) or a scheduled `scp` of the pulled snapshot dirs to a separate host. Enabling DigitalOcean droplet snapshots is a coarser alternative.

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
