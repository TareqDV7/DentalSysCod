# DentaCare cloud node — the multi-tenant Flask server (CLINIC_CLOUD_MODE=1).
# Build context is the repo root; see cloud/docker-compose.yml.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY dental_clinic.py ./
# dental_clinic.py imports templates.py at module load (the portal/login/mobile
# HTML lives there), so the cloud image needs it even though the staff portal
# isn't served on the cloud node — without it the container crash-loops on start.
# templates.py itself imports web_assets.py (inlined font/icon data) at module
# load, so that has to ship too.
COPY templates.py web_assets.py ./
# dental_clinic.py also imports the Data-Tools helpers (db_import / db_merge) at
# module load. The /api/data/* routes are 404 on the cloud node, but the top-level
# import still runs, so the image needs these (pure-stdlib) files or it crash-loops.
COPY db_import.py db_merge.py ./
# Every other same-directory module dental_clinic.py imports at the top of the
# file (module load, unconditional on CLOUD_MODE) — auth_codes (OTP/recovery),
# email_templates (relay rendering, the relay endpoint lives HERE on the cloud
# node), permissions, patient_dedupe, inventory, patient_import. All pure
# stdlib. Missing any one of these crash-loops the container on start; this
# whole block has bitten every redeploy so far because nothing enforces it —
# if dental_clinic.py grows a new top-level `import <local_module>`, add it
# here too.
COPY auth_codes.py email_templates.py permissions.py patient_dedupe.py inventory.py patient_import.py ./
# It also imports window.data_dir (resolve_data_dir, honors CLINIC_DATA_DIR=/data
# set below) and window.service_port (SERVICE_PORT_FILENAME) at module load — both
# pure stdlib, no GUI deps. The GUI submodules (pywebview etc.) are not imported
# on the cloud path and are intentionally left out of the image.
COPY window/__init__.py window/data_dir.py window/service_port.py ./window/
# /logo serves DentaCare.PNG if present (returns 204 otherwise) — copied opportunistically.
# (kept as a separate optional layer so the build still works if the asset isn't in the context)

ENV CLINIC_CLOUD_MODE=1 \
    CLINIC_DEBUG=0 \
    CLINIC_HOST=0.0.0.0 \
    CLINIC_PORT=5000 \
    CLINIC_DATA_DIR=/data
# Backups: rely on the default cadence (CLINIC_BACKUP_INTERVAL_HOURS=6,
# CLINIC_BACKUP_RETENTION=20). The backup worker snapshots cloud_master.db plus
# every discovered clinic_<id>.db into /data/backups/<label>/. Override either env
# var here or in docker-compose to tune.

EXPOSE 5000
CMD ["python", "dental_clinic.py"]
