import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/utils/sync_outcome.dart';

void main() {
  group('syncRoundSucceeded', () {
    test('succeeds only when both legs complete', () {
      expect(syncRoundSucceeded(pullOk: true, pushOk: true), isTrue);
    });

    test('fails when the push leg fails even if pull succeeded', () {
      expect(syncRoundSucceeded(pullOk: true, pushOk: false), isFalse);
    });

    test('fails when the pull leg fails even if push succeeded', () {
      expect(syncRoundSucceeded(pullOk: false, pushOk: true), isFalse);
    });

    test('fails when both legs fail', () {
      expect(syncRoundSucceeded(pullOk: false, pushOk: false), isFalse);
    });
  });
}
