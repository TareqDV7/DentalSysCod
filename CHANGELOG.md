# Changelog

## 2026-05-11

- Cloud tier added on top of the local server + mobile app: `sync_tombstones` + incremental `/api/sync/export?since=` (deletions now propagate); `CLINIC_CLOUD_MODE` runs `dental_clinic.py` multi-tenant as the cloud node (`app.dentacare.tech`, Docker + Caddy); `cloud_sync_worker()` mirrors a clinic's local server to/from the cloud in the background, managed from **Settings → Cloud Sync** (`/api/cloud/{pair,status,sync-now,unpair}`) with a dashboard status badge. See `DEPLOY_CLOUD.md`.
- Patient follow-up sheet: the *Add Entry* date is now a Day / Month / Year dropdown set (defaulting to today) instead of a free-text field; editing an entry closes the patient profile window and opens the edit window on its own (Save / Cancel return to the profile).
- Fixed the clinic-profit calculation in the follow-up sheet: clinic profit is now `price − discount − lab expense` (the discount given to the patient was previously ignored). Applied on add, edit, and in the summary/monthly report aggregates; the per-row "Profit" column is computed the same way.
- Test suite: 39 tests across six suites (added `test_sync_tombstones.py`, `test_cloud_mode.py`, `test_cloud_sync_worker.py`).

## 2026-05-04

- Normalized report date filters in `dental_clinic.py` so summary endpoints reject invalid dates and accept ISO or display-formatted input.
- Removed duplicated appointment row mapping by adding a shared serializer for appointment API responses.
- Hardened appointment status updates with validation and 404 handling when the record does not exist.
- Moved initial mobile sync off the app startup critical path in `clinic_mobile_app/lib/state/app_state.dart` so the UI becomes responsive sooner.
- Improved Dio error extraction in `clinic_mobile_app/lib/services/api_client.dart` to surface server errors and status codes more clearly.
- Updated `verify_reports.py` to cover invalid summary dates and invalid appointment status updates.
- Stabilized the Flutter widget smoke test so it verifies startup behavior without depending on live sync completion.