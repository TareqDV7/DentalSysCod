import '../models/patient.dart';
import '../models/appointment.dart';
import '../models/visit.dart';
import '../models/billing_record.dart';
import '../models/expense.dart';
import '../models/followup.dart';
import '../models/holiday.dart';
import '../models/treatment_plan.dart';
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

  /// Apply a sync export response (from server or Bluetooth peer) to the local DB.
  /// [response] should be the full export response map containing 'tables' and
  /// 'tombstones' keys (the same shape returned by /api/sync/export).
  ///
  /// Also advances the `last_sync_cursor` to the server's `generated_at` so the
  /// next pull (HTTP or Bluetooth) is incremental — critical for the BT path,
  /// which would otherwise re-pull the entire database every 30 s and could
  /// overwrite unpushed local edits with stale server rows.
  Future<void> applyExportedDelta(Map<String, dynamic> response) async {
    final tables = response['tables'];
    if (tables is Map) {
      await _mergeTables(Map<String, dynamic>.from(tables));
    }
    final tombstones = response['tombstones'];
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
    final generatedAt = response['generated_at']?.toString();
    if (generatedAt != null && generatedAt.isNotEmpty) {
      await _db.setSyncMeta('last_sync_cursor', generatedAt);
    }
  }

  /// Mark every row + tombstone in [payload] as synced.
  ///
  /// Called by the Bluetooth fallback path after the peer accepted our import,
  /// mirroring what [_pushToServer] does after a successful HTTP push. Without
  /// this, BT-pushed rows stay flagged `is_synced=0` forever and get re-sent
  /// every cycle.
  Future<void> markPayloadAsSynced(Map<String, dynamic> payload) async {
    final tables = payload['tables'];
    if (tables is Map) {
      for (final entry in DatabaseService.localToRemoteTable.entries) {
        final rows = tables[entry.value];
        if (rows is! List) continue;
        for (final r in rows) {
          if (r is Map && r['id'] is int) {
            await _db.markSynced(entry.key, r['id'] as int);
          }
        }
      }
    }
    final tombstones = payload['tombstones'];
    if (tombstones is List && tombstones.isNotEmpty) {
      await _db.markAllTombstonesSynced();
    }
  }

  /// Build the payload to push to the server (or Bluetooth peer).
  /// Returns {'tables': ..., 'tombstones': ...}.
  Future<Map<String, dynamic>> buildPushPayload() async {
    final tables = <String, dynamic>{};
    for (final entry in DatabaseService.localToRemoteTable.entries) {
      final localTable = entry.key;
      final remoteTable = entry.value;
      final rows = await _db.getUnsyncedRows(localTable);
      if (rows.isEmpty) continue;
      tables[remoteTable] =
          rows.map((r) => _toServerRow(localTable, r)).toList();
    }
    final tombstones = await _db.getUnsyncedTombstones();
    return {'tables': tables, 'tombstones': tombstones};
  }

  /// Returns the server's `generated_at` (cursor for the next incremental pull).
  Future<String?> _pullFromServer() async {
    try {
      final since = await _db.getSyncMeta('last_sync_cursor');
      final snapshot = await _api.get(
        '/api/sync/export',
        query: (since != null && since.isNotEmpty) ? {'since': since} : null,
      );
      await applyExportedDelta(snapshot);
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
    await each('patient_followups',
        (f) => _db.upsertFollowup(Followup.fromJson(f).copyWith(isSynced: true)));
    await each(
        'treatment_plans',
        (p) => _db.upsertTreatmentPlan(
            TreatmentPlan.fromJson(p).copyWith(isSynced: true)));
    await each('holidays',
        (h) => _db.upsertHoliday(Holiday.fromJson(h).copyWith(isSynced: true)));
  }

  Future<void> _pushToServer() async {
    final pushedRows = <String, List<int>>{};
    for (final entry in DatabaseService.localToRemoteTable.entries) {
      final localTable = entry.key;
      final rows = await _db.getUnsyncedRows(localTable);
      pushedRows[localTable] = [
        for (final r in rows)
          if (r['id'] is int) r['id'] as int,
      ];
    }

    final payload = await buildPushPayload();
    final tables = payload['tables'] as Map<String, dynamic>;
    final tombstones = payload['tombstones'] as List;
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
  ///
  /// [localTable] is the local table name (e.g. "billing_records") so we can
  /// apply table-specific shaping. The server otherwise drops unknown columns
  /// silently, which silently loses data — every drift we know about is handled
  /// explicitly here.
  Map<String, dynamic> _toServerRow(String localTable, Map<String, dynamic> row) {
    final out = Map<String, dynamic>.from(row);
    out.remove('is_synced');
    out.remove('patient_name'); // server-side join column, not a real column

    void rename(String from, String to) {
      if (out.containsKey(from)) out[to] = out.remove(from);
    }

    switch (localTable) {
      case 'appointments':
        rename('appointment_datetime', 'appointment_date');
        rename('duration_minutes', 'duration');
        break;
      case 'visits':
        rename('procedure_name', 'treatment_procedure');
        break;
      case 'billing_records':
        // server billing.amount is NOT NULL — fill it from subtotal − discount
        // when the local row only carries subtotal/discount.
        if (out['amount'] == null) {
          final sub = (out['subtotal'] is num) ? (out['subtotal'] as num).toDouble() : 0.0;
          final disc = (out['discount'] is num) ? (out['discount'] as num).toDouble() : 0.0;
          out['amount'] = sub - disc;
        }
        break;
      case 'expenses':
        // local "status" → server "payment_status"
        rename('status', 'payment_status');
        break;
      case 'treatment_procedures':
        // local lab_expense/is_active → server default_lab_expense/active
        rename('lab_expense', 'default_lab_expense');
        rename('is_active', 'active');
        break;
    }
    return out;
  }

  Future<String?> getLastSyncTime() => _db.getSyncMeta('last_sync');
}
