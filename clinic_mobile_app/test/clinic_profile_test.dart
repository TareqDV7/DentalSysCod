import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/utils/clinic_profile.dart';

void main() {
  group('resolveDoctorName', () {
    test('English locale shows the English name', () {
      expect(resolveDoctorName('Dr. Wasfy', 'د. وصفي', 'en'), 'Dr. Wasfy');
    });

    test('Arabic locale shows the Arabic name', () {
      expect(resolveDoctorName('Dr. Wasfy', 'د. وصفي', 'ar'), 'د. وصفي');
    });

    test('falls back to the other language when the preferred one is blank', () {
      expect(resolveDoctorName('Dr. Wasfy', '', 'ar'), 'Dr. Wasfy');
      expect(resolveDoctorName('  ', 'د. وصفي', 'en'), 'د. وصفي');
    });

    test('trims surrounding whitespace', () {
      expect(resolveDoctorName('  Dr. Wasfy  ', 'د. وصفي', 'en'), 'Dr. Wasfy');
    });

    test('returns empty string only when both are blank', () {
      expect(resolveDoctorName('', '   ', 'en'), '');
    });
  });
}
