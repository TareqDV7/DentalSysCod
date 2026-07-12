import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/models/appointment.dart';
import 'package:clinic_mobile_app/models/followup.dart';
import 'package:clinic_mobile_app/models/billing_record.dart';

void main() {
  group('Appointment dentistId', () {
    test('fromJson reads dentist_id', () {
      final a = Appointment.fromJson({
        'id': 1, 'patient_id': 2, 'appointment_datetime': '2026-08-01 10:00:00',
        'status': 'scheduled', 'dentist_id': 7,
      });
      expect(a.dentistId, 7);
    });

    test('fromJson tolerates missing dentist_id', () {
      final a = Appointment.fromJson({
        'id': 1, 'patient_id': 2, 'appointment_datetime': '2026-08-01 10:00:00', 'status': 'scheduled',
      });
      expect(a.dentistId, isNull);
    });

    test('toDb/fromDb round-trips dentist_id', () {
      final a = Appointment(
        patientId: 2, appointmentDatetime: '2026-08-01 10:00:00', dentistId: 9,
      );
      final restored = Appointment.fromDb(a.toDb());
      expect(restored.dentistId, 9);
    });

    test('toJson includes dentist_id when set', () {
      final a = Appointment(patientId: 2, appointmentDatetime: '2026-08-01 10:00:00', dentistId: 5);
      expect(a.toJson()['dentist_id'], 5);
    });
  });

  group('Followup dentistId', () {
    test('toDb/fromDb round-trips dentist_id', () {
      final f = Followup(patientId: 2, followupDate: '2026-08-01', treatmentProcedure: 'Filling', dentistId: 4);
      final restored = Followup.fromDb(f.toDb());
      expect(restored.dentistId, 4);
    });
  });

  group('BillingRecord dentistId', () {
    test('toDb/fromDb round-trips dentist_id', () {
      final b = BillingRecord(patientId: 2, subtotal: 100, paidAmount: 100, dentistId: 3);
      final restored = BillingRecord.fromDb(b.toDb());
      expect(restored.dentistId, 3);
    });
  });
}
