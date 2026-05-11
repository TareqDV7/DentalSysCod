import 'dart:convert';
import '../models/patient.dart';
import '../models/appointment.dart';
import '../models/visit.dart';
import '../models/billing_record.dart';
import '../models/expense.dart';
import '../models/treatment_procedure.dart';
import 'database_service.dart';
import 'clinic_api.dart';

class InternetSyncService {
  final DatabaseService _db;
  final ClinicApi _api;

  InternetSyncService(this._db, this._api);

  Future<void> syncAll() async {
    await _pullFromServer();
    await _pushToServer();
    await _db.setSyncMeta('last_sync', DateTime.now().toIso8601String());
  }

  Future<void> _pullFromServer() async {
    try {
      final snapshot = await _api.get('/api/sync/export');
      await _mergeSnapshot(snapshot);
    } catch (_) {
      // pull failures are non-fatal; we'll retry next sync
    }
  }

  Future<void> _mergeSnapshot(Map<String, dynamic> snapshot) async {
    final patients = (snapshot['patients'] as List? ?? []);
    for (final p in patients) {
      await _db.upsertPatient(Patient.fromJson(p as Map<String, dynamic>)
          .copyWith(isSynced: true));
    }

    final appointments = (snapshot['appointments'] as List? ?? []);
    for (final a in appointments) {
      await _db.upsertAppointment(
          Appointment.fromJson(a as Map<String, dynamic>)
              .copyWith(isSynced: true));
    }

    final visits = (snapshot['visits'] as List? ?? []);
    for (final v in visits) {
      await _db.upsertVisit(Visit.fromJson(v as Map<String, dynamic>));
    }

    final billing = (snapshot['billing'] as List? ?? []);
    for (final b in billing) {
      await _db.upsertBillingRecord(
          BillingRecord.fromJson(b as Map<String, dynamic>));
    }

    final expenses = (snapshot['expenses'] as List? ?? []);
    for (final e in expenses) {
      await _db.upsertExpense(Expense.fromJson(e as Map<String, dynamic>));
    }

    final procedures = (snapshot['treatment_procedures'] as List? ?? []);
    for (final p in procedures) {
      await _db.upsertProcedure(
          TreatmentProcedure.fromJson(p as Map<String, dynamic>));
    }
  }

  Future<void> _pushToServer() async {
    final tableMap = {
      'patients': 'patients',
      'appointments': 'appointments',
      'visits': 'visits',
      'billing_records': 'billing',
      'expenses': 'expenses',
    };

    final delta = <String, dynamic>{};
    for (final entry in tableMap.entries) {
      final rows = await _db.getUnsyncedRows(entry.key);
      if (rows.isNotEmpty) delta[entry.value] = rows;
    }

    if (delta.isEmpty) return;

    try {
      await _api.post('/api/sync/import', body: {'snapshot': delta});
      // mark all pushed rows as synced
      for (final table in tableMap.keys) {
        final rows = await _db.getUnsyncedRows(table);
        for (final row in rows) {
          if (row['id'] != null) {
            await _db.markSynced(table, row['id'] as int);
          }
        }
      }
    } catch (_) {
      // push failures are non-fatal
    }
  }

  Future<String?> getLastSyncTime() => _db.getSyncMeta('last_sync');
}

// ignore: unused_element
String _encode(dynamic obj) => jsonEncode(obj);
