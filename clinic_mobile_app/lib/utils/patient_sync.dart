import '../models/patient.dart';

/// Reconcile a just-created patient against the server's create response.
///
/// The desktop's `POST /api/patients` historically returned only
/// `{'success': true}` — no row. The old code rebuilt the patient from that
/// response (`Patient.fromJson`), producing a blank-named row that overwrote
/// the one the user just typed and then crashed the list on render. We instead
/// keep every field the user entered and only adopt the server-assigned `id`
/// when the response actually carries one (top-level `id` or nested
/// `patient.id`); otherwise we keep the local id. The names in the response are
/// never trusted. The row is always marked synced.
Patient reconcileCreatedPatient(
    Patient local, int localId, Map<String, dynamic> response) {
  final nested = response['patient'];
  final serverId = _asInt(response['id']) ??
      (nested is Map ? _asInt(nested['id']) : null);
  return local.copyWith(id: serverId ?? localId, isSynced: true);
}

int? _asInt(Object? v) {
  if (v is int) return v;
  if (v is String) return int.tryParse(v);
  return null;
}
