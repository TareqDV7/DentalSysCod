# Changelog

## 2026-05-04

- Normalized report date filters in `dental_clinic.py` so summary endpoints reject invalid dates and accept ISO or display-formatted input.
- Removed duplicated appointment row mapping by adding a shared serializer for appointment API responses.
- Hardened appointment status updates with validation and 404 handling when the record does not exist.
- Moved initial mobile sync off the app startup critical path in `clinic_mobile_app/lib/state/app_state.dart` so the UI becomes responsive sooner.
- Improved Dio error extraction in `clinic_mobile_app/lib/services/api_client.dart` to surface server errors and status codes more clearly.
- Updated `verify_reports.py` to cover invalid summary dates and invalid appointment status updates.
- Stabilized the Flutter widget smoke test so it verifies startup behavior without depending on live sync completion.