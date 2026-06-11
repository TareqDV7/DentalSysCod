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
COPY templates.py ./
# dental_clinic.py also imports the Data-Tools helpers (db_import / db_merge) at
# module load. The /api/data/* routes are 404 on the cloud node, but the top-level
# import still runs, so the image needs these (pure-stdlib) files or it crash-loops.
COPY db_import.py db_merge.py ./
# It also does `from window.data_dir import resolve_data_dir` at module load.
# Only data_dir.py (pure stdlib) + the package __init__ (docstring only, no
# imports) are needed on the cloud path; the GUI submodules are not imported.
# resolve_data_dir() honors CLINIC_DATA_DIR=/data (set below), so the cloud
# node stores its SQLite files on the mounted volume as before.
COPY window/__init__.py window/data_dir.py ./window/
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
