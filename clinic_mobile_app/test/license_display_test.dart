import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/utils/license_display.dart';

void main() {
  group('maskSerial', () {
    test('shows only the last four characters', () {
      expect(maskSerial('DENTAL-ABCD-1234'), '••••1234');
    });

    test('returns short serials unmasked', () {
      expect(maskSerial('AB12'), 'AB12');
      expect(maskSerial('X'), 'X');
    });

    test('empty stays empty', () {
      expect(maskSerial('   '), '');
    });
  });

  group('licenseExpiryDate', () {
    test('extracts the YYYY-MM-DD date from an ISO timestamp', () {
      expect(licenseExpiryDate('2027-01-15T00:00:00Z'), '2027-01-15');
    });

    test('accepts a bare date', () {
      expect(licenseExpiryDate('2027-01-15'), '2027-01-15');
    });

    test('returns null for blank or malformed input', () {
      expect(licenseExpiryDate(null), isNull);
      expect(licenseExpiryDate(''), isNull);
      expect(licenseExpiryDate('not-a-date'), isNull);
      expect(licenseExpiryDate('15/01/2027'), isNull);
    });
  });
}
