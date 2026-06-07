import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/connectivity_sync_service.dart';
import 'package:clinic_mobile_app/utils/sync_banner.dart';

void main() {
  group('syncBannerBehavior', () {
    test('idle is not shown', () {
      final b = syncBannerBehavior(SyncStatus.idle);
      expect(b.show, isFalse);
      expect(b.autoHide, isNull);
    });

    test('syncing stays visible until it resolves (no auto-hide)', () {
      final b = syncBannerBehavior(SyncStatus.syncing);
      expect(b.show, isTrue);
      expect(b.autoHide, isNull);
    });

    test('synced shows briefly then auto-hides', () {
      final b = syncBannerBehavior(SyncStatus.synced);
      expect(b.show, isTrue);
      expect(b.autoHide, const Duration(seconds: 3));
    });

    test('offline and error linger a little longer, then auto-hide', () {
      for (final s in [SyncStatus.offline, SyncStatus.error]) {
        final b = syncBannerBehavior(s);
        expect(b.show, isTrue, reason: '$s should show');
        expect(b.autoHide, const Duration(seconds: 5), reason: '$s auto-hide');
      }
    });
  });

  group('shouldEmitSyncStatus (de-flicker)', () {
    test('suppresses an identical consecutive status + message', () {
      expect(
        shouldEmitSyncStatus(
            SyncStatus.synced, 'Synced · Cloud', SyncStatus.synced, 'Synced · Cloud'),
        isFalse,
      );
    });

    test('emits when the status changes', () {
      expect(
        shouldEmitSyncStatus(
            SyncStatus.synced, 'Synced · Cloud', SyncStatus.syncing, 'Syncing…'),
        isTrue,
      );
    });

    test('emits when only the message changes (e.g. a different link)', () {
      expect(
        shouldEmitSyncStatus(SyncStatus.synced, 'Synced · Cloud',
            SyncStatus.synced, 'Synced · Local Wi-Fi'),
        isTrue,
      );
    });
  });
}
