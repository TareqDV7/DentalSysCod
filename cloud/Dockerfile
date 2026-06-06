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
