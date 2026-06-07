import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/utils/app_strings.dart';

/// Guards the bilingual catalog against the two ways it silently breaks:
///   1. A key added to one language but not the other — AppStrings.t falls back
///      to the raw key, surfacing an English-looking token instead of a miss.
///   2. A blank value, or English text pasted into the Arabic map.
void main() {
  final en = AppStrings.translations['en']!;
  final ar = AppStrings.translations['ar']!;

  group('AppStrings catalog', () {
    test('English and Arabic have identical key sets', () {
      final missingAr = en.keys.toSet().difference(ar.keys.toSet());
      final missingEn = ar.keys.toSet().difference(en.keys.toSet());
      expect(missingAr, isEmpty, reason: 'Keys missing an Arabic value: $missingAr');
      expect(missingEn, isEmpty, reason: 'Keys missing an English value: $missingEn');
    });

    test('no value is blank', () {
      for (final e in en.entries) {
        expect(e.value.trim(), isNotEmpty, reason: 'Blank English value for "${e.key}"');
      }
      for (final e in ar.entries) {
        expect(e.value.trim(), isNotEmpty, reason: 'Blank Arabic value for "${e.key}"');
      }
    });

    test('Arabic is actually translated, not English copy-paste', () {
      // A few values may legitimately coincide across languages, so flag only a
      // systemic problem (>20% identical) rather than requiring every key differ.
      final identical = en.keys.where((k) => ar[k] == en[k]).toList();
      expect(identical.length, lessThan(en.length * 0.2),
          reason: '${identical.length}/${en.length} Arabic values equal English: $identical');
    });
  });
}
