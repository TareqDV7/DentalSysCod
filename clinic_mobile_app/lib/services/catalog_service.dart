import '../models/treatment_procedure.dart';
import 'clinic_api.dart';
import 'database_service.dart';

/// CRUD for the treatment-procedure catalog (server table
/// `treatment_procedures`). Mirrors the desktop's
/// `/api/treatment-procedures` endpoint pair: GET, POST, PUT (soft-delete
/// is a PUT with `active: false` — there is no DELETE on the server).
class CatalogService {
  final DatabaseService _db;
  final ClinicApi _api;

  CatalogService(this._db, this._api);

  Future<List<TreatmentProcedure>> getAll() => _db.getAllProcedures();
  Future<List<TreatmentProcedure>> getActive() => _db.getProcedures();

  Future<TreatmentProcedure> add(TreatmentProcedure p) async {
    final now = DateTime.now().toIso8601String();
    final local = p.copyWith(
      isActive: true,
      isSynced: false,
      updatedAt: now,
    );
    final localId = await _db.upsertProcedure(local);

    try {
      await _api.post('/api/treatment-procedures', body: local.toJson());
      // Server returns {success: true} only — re-fetch the catalog on the
      // next sync pull to pick up the server-assigned id. For now mark
      // the local row as synced so we don't double-push.
      final stored = local.copyWith(id: localId, isSynced: true);
      await _db.upsertProcedure(stored);
      return stored;
    } catch (_) {
      return local.copyWith(id: localId);
    }
  }

  Future<TreatmentProcedure> update(TreatmentProcedure p) async {
    if (p.id == null) {
      throw ArgumentError('CatalogService.update requires id');
    }
    final updated = p.copyWith(
      updatedAt: DateTime.now().toIso8601String(),
      isSynced: false,
    );
    await _db.upsertProcedure(updated);
    try {
      await _api.put('/api/treatment-procedures/${p.id}', body: updated.toJson());
      final stored = updated.copyWith(isSynced: true);
      await _db.upsertProcedure(stored);
      return stored;
    } catch (_) {
      return updated;
    }
  }

  /// Soft-delete: flips `is_active = 0` so the procedure stops appearing in
  /// pickers but historical follow-ups that referenced it keep working. The
  /// desktop server has no DELETE on this resource — we use PUT with
  /// `active: false`.
  Future<TreatmentProcedure> deactivate(TreatmentProcedure p) =>
      update(p.copyWith(isActive: false));

  Future<TreatmentProcedure> reactivate(TreatmentProcedure p) =>
      update(p.copyWith(isActive: true));
}
