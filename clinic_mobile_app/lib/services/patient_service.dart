import '../models/patient.dart';
import '../models/visit.dart';
import '../models/followup.dart';
import 'database_service.dart';
import 'clinic_api.dart';

class PatientService {
  final DatabaseService _db;
  final ClinicApi _api;

  PatientService(this._db, this._api);

  Future<List<Patient>> getPatients({String? query}) =>
      _db.getPatients(query: query);

  Future<Patient?> getPatient(int id) => _db.getPatient(id);

  /// Existing patients that collide on name or phone — for a non-blocking
  /// "already exists" warning before saving a new patient.
  Future<List<Patient>> findDuplicates({
    required String firstName,
    required String lastName,
    String? phone,
    int? excludeId,
  }) =>
      _db.findDuplicatePatients(
        firstName: firstName,
        lastName: lastName,
        phone: phone,
        excludeId: excludeId,
      );

  Future<Patient> addPatient(Patient p) async {
    final now = DateTime.now().toIso8601String();
    final local = p.copyWith(updatedAt: now, isSynced: false);
    final localId = await _db.upsertPatient(local);

    try {
      final res = await _api.post('/api/patients', body: local.toJson());
      final remote = Patient.fromJson(res);
      await _db.deletePatient(localId);
      await _db.upsertPatient(remote.copyWith(isSynced: true));
      return remote;
    } catch (_) {
      return local.copyWith(id: localId);
    }
  }

  Future<Patient> updatePatient(Patient p) async {
    final updated = p.copyWith(
        updatedAt: DateTime.now().toIso8601String(), isSynced: false);
    await _db.upsertPatient(updated);

    try {
      final res =
          await _api.post('/api/patients/${p.id}', body: updated.toJson());
      final remote = Patient.fromJson(res);
      await _db.upsertPatient(remote.copyWith(isSynced: true));
      return remote;
    } catch (_) {
      return updated;
    }
  }

  Future<void> deletePatient(int id) async {
    await _db.deletePatient(id);
    try {
      await _api.post('/api/patients/$id/delete', body: {});
    } catch (_) {}
  }

  Future<List<Visit>> getPatientVisits(int patientId) =>
      _db.getPatientVisits(patientId);

  Future<Visit> addVisit(Visit v) async {
    final localId = await _db.upsertVisit(
        v.withUpdatedAt(DateTime.now().toIso8601String()));

    try {
      final res = await _api
          .post('/api/patients/${v.patientId}/visits', body: v.toJson());
      final remote = Visit.fromJson(res);
      await _db.deleteVisit(localId);
      await _db.upsertVisit(remote);
      return remote;
    } catch (_) {
      return Visit.fromDb({...v.toDb(), 'id': localId, 'is_synced': 0});
    }
  }

  Future<Visit> updateVisit(int patientId, Visit v) async {
    await _db.upsertVisit(v.withUpdatedAt(DateTime.now().toIso8601String()));

    try {
      final res = await _api.put(
          '/api/patients/$patientId/followups/${v.id}',
          body: {
            'treatment_procedure': v.procedureName,
            'followup_date': v.visitDate,
            'price': v.price ?? 0,
            'lab_expense': v.labExpense ?? 0,
            'payment': v.payment ?? 0,
            'notes': v.notes,
          });
      if (res['success'] == true) {
        final updated = v.copyWith(isSynced: true);
        await _db.upsertVisit(updated);
        return updated;
      }
      return v;
    } catch (_) {
      return v;
    }
  }

  Future<void> deleteVisit(int patientId, int visitId) async {
    await _db.deleteVisit(visitId);
    try {
      await _api.delete('/api/patients/$patientId/followups/$visitId');
    } catch (_) {}
  }

  // ── Follow-ups (canonical patient ledger) ───────────────────────────────────
  //
  // Offline-first: writes go to the local sqflite + record `is_synced=0` and
  // a recompute fires on the patient's whole ledger. The next sync cycle
  // pushes the row to the server, which runs its own canonical recompute and
  // emits the new `remaining_amount` back on the following pull. Callers that
  // want the desktop to see the row immediately should trigger
  // `ConnectivitySyncService.syncNow()` after the write.

  Future<List<Followup>> getPatientFollowups(int patientId) =>
      _db.getPatientFollowups(patientId);

  Future<int> addFollowup(Followup f) {
    return _db.upsertFollowup(
        f.copyWith(updatedAt: DateTime.now().toIso8601String(), isSynced: false));
  }

  Future<int> updateFollowup(Followup f) {
    return _db.upsertFollowup(
        f.copyWith(updatedAt: DateTime.now().toIso8601String(), isSynced: false));
  }

  Future<void> deleteFollowup({required int patientId, required int id}) =>
      _db.deleteFollowup(id: id, patientId: patientId);
}

extension _VisitExt on Visit {
  Visit withUpdatedAt(String t) => Visit(
        id: id,
        patientId: patientId,
        patientName: patientName,
        visitDate: visitDate,
        procedureName: procedureName,
        price: price,
        labExpense: labExpense,
        payment: payment,
        notes: notes,
        updatedAt: t,
        isSynced: false,
      );
}
