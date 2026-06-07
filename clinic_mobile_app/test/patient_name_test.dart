import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/utils/patient_name.dart';

void main() {
  group('resolvePatientName', () {
    test('prefers a non-blank stored name over the joined patient', () {
      expect(
        resolvePatientName('John Doe', firstName: 'Jane', lastName: 'Roe'),
        'John Doe',
      );
    });

    test('falls back to joined first+last when stored is null', () {
      expect(
        resolvePatientName(null, firstName: 'Jane', lastName: 'Roe'),
        'Jane Roe',
      );
    });

    test('falls back when stored is empty or whitespace', () {
      expect(
        resolvePatientName('   ', firstName: 'Jane', lastName: 'Roe'),
        'Jane Roe',
      );
    });

    test('treats the literal string "null" as blank (sqlite/json drift)', () {
      expect(
        resolvePatientName('null', firstName: 'Jane', lastName: 'Roe'),
        'Jane Roe',
      );
    });

    test('handles a missing last name', () {
      expect(
        resolvePatientName(null, firstName: 'Madonna', lastName: ''),
        'Madonna',
      );
    });

    test('returns null when neither stored nor joined name is usable', () {
      expect(resolvePatientName(null, firstName: null, lastName: null), isNull);
      expect(resolvePatientName('', firstName: '', lastName: ''), isNull);
      expect(resolvePatientName('  null ', firstName: ' ', lastName: null),
          isNull);
    });
  });

  group('patientInitials', () {
    test('builds two-letter initials from first and last', () {
      expect(patientInitials('Jane', 'Roe'), 'JR');
    });

    test('uses only the first letter when the last name is empty', () {
      expect(patientInitials('Madonna', ''), 'M');
    });

    test('uses only the last initial when the first name is blank', () {
      expect(patientInitials('', 'Smith'), 'S');
    });

    test('returns "?" instead of indexing an empty string', () {
      // _PatientTile used to do firstName[0] — a RangeError on a blank row that
      // white-screened the whole patients list. This must never throw.
      expect(patientInitials('', ''), '?');
      expect(patientInitials('   ', '  '), '?');
    });

    test('keeps Arabic initials intact', () {
      expect(patientInitials('وصفي', 'برزق'), 'وب');
    });
  });
}
