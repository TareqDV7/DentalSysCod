import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/models/appointment.dart';
import 'package:clinic_mobile_app/utils/appointment_overlap.dart';

Appointment _appt({
  int? id,
  required String at,
  int? duration,
  String status = 'scheduled',
}) =>
    Appointment(
      id: id,
      patientId: 1,
      appointmentDatetime: at,
      durationMinutes: duration,
      status: status,
    );

void main() {
  group('appointmentsOverlap', () {
    final nine = DateTime(2026, 6, 9, 9, 0);

    test('ranges that share time overlap', () {
      final overlapping = DateTime(2026, 6, 9, 9, 15);
      expect(appointmentsOverlap(nine, 30, overlapping, 30), isTrue);
    });

    test('back-to-back slots do not overlap', () {
      final next = DateTime(2026, 6, 9, 9, 30); // starts as the first ends
      expect(appointmentsOverlap(nine, 30, next, 30), isFalse);
    });

    test('fully separate ranges do not overlap', () {
      final later = DateTime(2026, 6, 9, 11, 0);
      expect(appointmentsOverlap(nine, 30, later, 30), isFalse);
    });

    test('a longer first slot can swallow a later start', () {
      final inside = DateTime(2026, 6, 9, 9, 45);
      expect(appointmentsOverlap(nine, 60, inside, 15), isTrue);
    });
  });

  group('findAppointmentConflicts', () {
    final start = DateTime(2026, 6, 9, 9, 0);

    test('returns an overlapping scheduled appointment', () {
      final existing = [_appt(id: 1, at: '2026-06-09T09:15:00', duration: 30)];
      expect(findAppointmentConflicts(existing, start, 30), hasLength(1));
    });

    test('ignores completed and cancelled appointments', () {
      final existing = [
        _appt(id: 1, at: '2026-06-09T09:00:00', duration: 30, status: 'completed'),
        _appt(id: 2, at: '2026-06-09T09:00:00', duration: 30, status: 'cancelled'),
      ];
      expect(findAppointmentConflicts(existing, start, 30), isEmpty);
    });

    test('ignores the appointment being edited via excludeId', () {
      final existing = [_appt(id: 7, at: '2026-06-09T09:00:00', duration: 30)];
      expect(
        findAppointmentConflicts(existing, start, 30, excludeId: 7),
        isEmpty,
      );
    });

    test('falls back to the default slot length when duration is null', () {
      // No duration → treated as 30 min, so a 09:20 start overlaps a 09:00 slot.
      final existing = [_appt(id: 1, at: '2026-06-09T09:00:00')];
      final at920 = DateTime(2026, 6, 9, 9, 20);
      expect(findAppointmentConflicts(existing, at920, 30), hasLength(1));
    });

    test('returns conflicts sorted by start time', () {
      final existing = [
        _appt(id: 1, at: '2026-06-09T09:50:00', duration: 30),
        _appt(id: 2, at: '2026-06-09T09:10:00', duration: 30),
      ];
      final conflicts = findAppointmentConflicts(existing, start, 120);
      expect(conflicts.map((a) => a.id).toList(), [2, 1]);
    });
  });
}
