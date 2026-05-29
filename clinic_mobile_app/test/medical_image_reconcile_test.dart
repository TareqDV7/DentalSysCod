import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/medical_image_service.dart';

void main() {
  group('MedicalImageService.missingServerImages (pull reconciliation)', () {
    test('returns only server rows absent from the local set', () {
      final result = MedicalImageService.missingServerImages(
        {1, 3},
        [
          {'id': 1, 'file_name': 'a.jpg'},
          {'id': 2, 'file_name': 'b.jpg'},
          {'id': 3, 'file_name': 'c.jpg'},
          {'id': 4, 'file_name': 'd.jpg'},
        ],
      );
      expect(result.map((r) => r['id']).toList(), [2, 4]);
    });

    test('empty local set → every server row is missing', () {
      final result = MedicalImageService.missingServerImages(
        <int>{},
        [
          {'id': 7, 'file_name': 'x.jpg'},
          {'id': 9, 'file_name': 'y.jpg'},
        ],
      );
      expect(result.map((r) => r['id']).toList(), [7, 9]);
    });

    test('coerces string ids and normalizes them to int', () {
      final result = MedicalImageService.missingServerImages(
        {5},
        [
          {'id': '5', 'file_name': 'have.jpg'},
          {'id': '6', 'file_name': 'want.jpg'},
        ],
      );
      expect(result.length, 1);
      expect(result.single['id'], 6);
      expect(result.single['id'], isA<int>());
    });

    test('skips malformed rows (non-map and unparseable id)', () {
      final result = MedicalImageService.missingServerImages(
        <int>{},
        [
          'not a map',
          {'file_name': 'no-id.jpg'},
          {'id': 'abc', 'file_name': 'bad-id.jpg'},
          {'id': 11, 'file_name': 'good.jpg'},
        ],
      );
      expect(result.length, 1);
      expect(result.single['id'], 11);
    });

    test('empty server listing → nothing to fetch', () {
      expect(
        MedicalImageService.missingServerImages({1, 2}, const []),
        isEmpty,
      );
    });
  });
}
