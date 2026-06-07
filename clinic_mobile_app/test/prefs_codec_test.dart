import 'package:flutter/material.dart' show ThemeMode;
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/utils/prefs_codec.dart';

void main() {
  group('theme mode codec', () {
    test('round-trips every mode', () {
      for (final mode in ThemeMode.values) {
        expect(decodeThemeMode(encodeThemeMode(mode)), mode);
      }
    });

    test('decodes a persisted dark value', () {
      expect(decodeThemeMode('dark'), ThemeMode.dark);
    });

    test('falls back to light for null or unknown', () {
      expect(decodeThemeMode(null), ThemeMode.light);
      expect(decodeThemeMode(''), ThemeMode.light);
      expect(decodeThemeMode('nonsense'), ThemeMode.light);
    });
  });

  group('locale codec', () {
    test('keeps Arabic', () {
      expect(decodeLocale('ar'), 'ar');
    });

    test('defaults to English for null, en, or unsupported', () {
      expect(decodeLocale(null), 'en');
      expect(decodeLocale('en'), 'en');
      expect(decodeLocale('fr'), 'en');
    });
  });
}
