import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/models/marketing_post.dart';

void main() {
  group('MarketingPost.fromJson', () {
    test('parses a full server row correctly', () {
      final post = MarketingPost.fromJson({
        'id': 7,
        'theme': 'classic',
        'size': 'square',
        'doctor_name': 'Dr. Smith',
        'photo_count': 2,
        'created_at': '2026-06-25T10:30:00',
      });

      expect(post.id, 7);
      expect(post.theme, 'classic');
      expect(post.size, 'square');
      expect(post.doctorName, 'Dr. Smith');
      expect(post.photoCount, 2);
      expect(post.createdAt, '2026-06-25T10:30:00');
    });

    test('coerces numeric id from double', () {
      final post = MarketingPost.fromJson({
        'id': 3.0,
        'theme': 'bold',
        'size': 'portrait',
        'doctor_name': '',
        'photo_count': 1,
      });
      expect(post.id, 3);
      expect(post.id, isA<int>());
    });

    test('handles missing optional created_at', () {
      final post = MarketingPost.fromJson({
        'id': 1,
        'theme': 'modern',
        'size': 'landscape',
        'doctor_name': 'Dr. Ali',
        'photo_count': 4,
      });
      expect(post.createdAt, isNull);
    });

    test('handles string photo_count gracefully', () {
      final post = MarketingPost.fromJson({
        'id': 5,
        'theme': 'classic',
        'size': 'square',
        'doctor_name': '',
        'photo_count': '3',
      });
      expect(post.photoCount, 3);
    });

    test('defaults empty strings for missing name fields', () {
      final post = MarketingPost.fromJson({'id': 9, 'photo_count': 0});
      expect(post.theme, '');
      expect(post.size, '');
      expect(post.doctorName, '');
    });

    test('toJson round-trips correctly', () {
      const original = MarketingPost(
        id: 12,
        theme: 'bold',
        size: 'square',
        doctorName: 'Dr. Nour',
        photoCount: 1,
        createdAt: '2026-06-26',
      );
      final json = original.toJson();
      final restored = MarketingPost.fromJson(json);

      expect(restored.id, original.id);
      expect(restored.theme, original.theme);
      expect(restored.size, original.size);
      expect(restored.doctorName, original.doctorName);
      expect(restored.photoCount, original.photoCount);
      expect(restored.createdAt, original.createdAt);
    });
  });
}
