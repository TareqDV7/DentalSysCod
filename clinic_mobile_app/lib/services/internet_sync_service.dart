import '../models/patient.dart';
import '../models/appointment.dart';
import '../models/visit.dart';
import '../models/billing_record.dart';
import '../models/expense.dart';
import '../models/treatment_procedure.dart';
import 'database_service.dart';
import 'clinic_api.dart';

/// Syncs the local SQLite database with a clinic server over HTTP. Works against
/// either a LAN/local server (device-token auth) or the shared cloud node
/// (clinic-token auth) — whichever the caller has pointed [ClinicApi] at.
class InternetSyncService {
  final DatabaseService _db;
  final ClinicApi _api;

  InternetSyncService(this._db, this._api);

  Future<void> syncAll() async {
    final generatedAt = await _pullFromServer();
    await _pushToServer();
    await _db.setSyncMeta('last_sync', DateTime.now().toIso8601String());
    if (generatedAt != null && generatedAt.isNotEmpty) {
      // Use the server's own clock as the cursor for the next incremental pull.
      await _db.setSyncMeta('last_sync_cursor', generatedAt);
    }
  }

  /// Returns the server's `generated_at` (cursor for the next incremental pull).
  Future<String?> _pullFromServer() async {
    try {
      final since = await _db.getSyncMeta('last_sync_cursor');
      final snapshot = await _api.get(
        '/api/sync/export',
        query: (since != null && since.isNotEmpty) ? {'since': since} : null,
      );
      final tables = snapshot['tables'];
      if (tables is Map) {
        await _mergeTables(Map<String, dynamic>.from(tables));
      }
      final tombstones = snapshot['tombstones'];
      if (tombstones is List) {
        for (final t in tombstones) {
          if (t is Map && t['table_name'] != null && t['row_id'] != null) {
            final rowId = int.tryParse('${t['row_id']}');
            if (rowId != null) {
              await _db.applyTombstone(t['table_name'].toString(), rowId);
            }
          }
        }
      }
      return snapshot['generated_at']?.toString();
    } catch (_) {
      // pull failures are non-fatal; we'll retry next sync
      return null;
    }
  }

  Future<void> _mergeTables(Map<String, dynamic> tables) async {
    Future<void> each(
        String key, Future<void> Function(Map<String, dynamic>) fn) async {
      final list = tables[key];
      if (list is! List) return;
      for (final row in list) {
        if (row is Map) {
          await fn(Map<String, dynamic>.from(row));
        }
      }
    }

    await each('patients',
        (p) => _db.upsertPatient(Patient.fromJson(p).copyWith(isSynced: true)));
    await each(
        'appointments',
        (a) => _db
            .upsertAppointment(Appointment.fromJson(a).copyWith(isSynced: true)));
    await each('visits', (v) => _db.upsertVisit(Visit.fromJson(v)));
    await each(
        'billing', (b) => _db.upsertBillingRecord(BillingRecord.fromJson(b)));
    await each('expenses', (e) => _db.upsertExpense(Expense.fromJson(e)));
    await each('treatment_procedures',
        (p) => _db.upsertProcedure(TreatmentProcedure.fromJson(p)));
  }

  Future<void> _pushToServer() async {
    final tables = <String, dynamic>{};
    final pushedRows = <String, List<int>>{};
    for (final entry in DatabaseService.localToRemoteTable.entries) {
      final localTable = entry.key;
      final remoteTable = entry.value;
      final rows = await _db.getUnsyncedRows(localTable);
      if (rows.isEmpty) continue;
      tables[remoteTable] = rows.map(_toServerRow).toList();
      pushedRows[localTable] = [
        for (final r in rows)
          if (r['id'] is int) r['id'] as int,
      ];
    }

    final tombstones = await _db.getUnsyncedTombstones();
    if (tables.isEmpty && tombstones.isEmpty) return;

    try {
      await _api.post('/api/sync/import',
          body: {'tables': tables, 'tombstones': tombstones});
      for (final entry in pushedRows.entries) {
        for (final id in entry.value) {
          await _db.markSynced(entry.key, id);
        }
      }
      await _db.markAllTombstonesSynced();
    } catch (_) {
      // push failures are non-fatal
    }
  }

  /// Adapt a local row to the server's column names (the two schemas drifted a bit).
  Map<String, dynamic> _toServerRow(Map<String, dynamic> row) {
    final out = Map<String, dynamic>.from(row);
    out.remove('is_synced');
    out.remove('patient_name'); // server-side join column, not a real column

    void rename(String from, String to) {
      if (out.containsKey(from)) out[to] = out.remove(from);
    }

    rename('appointment_datetime', 'appointment_date');
    rename('duration_minutes', 'duration');
    rename('procedure_name', 'treatment_procedure');
    if (out.containsKey('status') && out.containsKey('amount')) {
      // expenses: local "status" maps to the server's "payment_status"
      rename('status', 'payment_status');
    }
    return out;
  }

  Future<String?> getLastSyncTime() => _db.getSyncMeta('last_sync');
}
