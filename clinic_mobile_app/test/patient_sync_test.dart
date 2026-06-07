import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/models/patient.dart';
import 'package:clinic_mobile_app/utils/patient_sync.dart';

void main() {
  group('reconcileCreatedPatient', () {
    final local = Patient(firstName: 'Wasfy', lastName: 'Barzaq', phone: '0599');

    test('keeps the locally-typed fields when the server omits the row', () {
      // The old desktop returned only {'success': true}; reconciling must NOT
      // blank the name (that wiped the just-added patient and crashed the list).
      final r = reconcileCreatedPatient(local, 12, {'success': true});
      expect(r.firstName, 'Wasfy');
      expect(r.lastName, 'Barzaq');
      expect(r.phone, '0599');
      expect(r.id, 12); // falls back to the local id when none is returned
      expect(r.isSynced, isTrue);
    });

    test('adopts a top-level server id but never trusts response names', () {
      final r = reconcileCreatedPatient(
          local, 12, {'success': true, 'id': 42, 'first_name': '', 'last_name': ''});
      expect(r.id, 42);
      expect(r.firstName, 'Wasfy');
      expect(r.lastName, 'Barzaq');
      expect(r.isSynced, isTrue);
    });

    test('adopts a nested patient.id', () {
      final r = reconcileCreatedPatient(local, 12, {
        'patient': {'id': 7}
      });
      expect(r.id, 7);
      expect(r.firstName, 'Wasfy');
    });

    test('accepts a numeric-string id', () {
      final r = reconcileCreatedPatient(local, 12, {'id': '99'});
      expect(r.id, 99);
    });
  });
}
