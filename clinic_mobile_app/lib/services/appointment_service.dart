import '../models/appointment.dart';
import 'database_service.dart';
import 'clinic_api.dart';
import 'api_client.dart';

class AppointmentService {
  final DatabaseService _db;
  final ClinicApi _api;

  AppointmentService(this._db, this._api);

  Future<List<Appointment>> getAppointments({DateTime? date}) =>
      _db.getAppointments(date: date);

  Future<List<Appointment>> getRecentAppointments({int limit = 10}) =>
      _db.getRecentAppointments(limit: limit);

  Future<List<Appointment>> getPatientAppointments(int patientId) =>
      _db.getPatientAppointments(patientId);

  Future<Map<DateTime, int>> getMonthCounts(int year, int month) =>
      _db.getAppointmentCountsByMonth(year, month);

  Future<Appointment> addAppointment(Appointment a) async {
    final now = DateTime.now().toIso8601String();
    final local = Appointment(
      patientId: a.patientId,
      patientName: a.patientName,
      appointmentDatetime: a.appointmentDatetime,
      durationMinutes: a.durationMinutes,
      treatmentType: a.treatmentType,
      status: a.status,
      notes: a.notes,
      updatedAt: now,
      isSynced: false,
    );
    final localId = await _db.upsertAppointment(local);

    try {
      final res = await _api.post('/api/appointments', body: local.toJson());
      final payload = (res['appointment'] is Map<String, dynamic>)
          ? (res['appointment'] as Map<String, dynamic>)
          : res;
      final remote = Appointment.fromJson(payload);
      await _db.deleteAppointment(localId);
      await _db.upsertAppointment(remote.copyWith(isSynced: true));
      return remote;
    } on ApiException catch (error) {
      if (!error.isNetwork && (error.statusCode ?? 500) < 500) {
        rethrow;
      }
      return Appointment.fromDb({...local.toDb(), 'id': localId});
    } catch (_) {
      return Appointment.fromDb({...local.toDb(), 'id': localId});
    }
  }

  Future<Appointment> updateStatus(int id, String status) async {
    final existing = (await _db.getAppointments())
        .where((a) => a.id == id)
        .firstOrNull;
    if (existing == null) throw Exception('Appointment $id not found');
    final updated = existing.copyWith(status: status, isSynced: false);
    await _db.upsertAppointment(updated);

    try {
      final res = await _api.put(
        '/api/appointments/$id/status',
        body: {'status': status},
      );
      if (res['appointment'] is Map<String, dynamic>) {
        final remote = Appointment.fromJson(res['appointment'] as Map<String, dynamic>);
        await _db.upsertAppointment(remote.copyWith(isSynced: true));
        return remote;
      }
      final synced = updated.copyWith(status: status, isSynced: true);
      await _db.upsertAppointment(synced);
      return synced;
    } on ApiException catch (error) {
      if (!error.isNetwork && (error.statusCode ?? 500) < 500) {
        rethrow;
      }
      return updated;
    } catch (_) {
      return updated;
    }
  }

  Future<void> deleteAppointment(int id) async {
    await _db.deleteAppointment(id);
    try {
      await _api.delete('/api/appointments/$id');
    } catch (_) {}
  }
}
