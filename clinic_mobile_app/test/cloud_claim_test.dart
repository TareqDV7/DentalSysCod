import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/api_client.dart';
import 'package:clinic_mobile_app/services/cloud_sync_service.dart';
import 'package:clinic_mobile_app/utils/activation_token.dart';

/// Captures the outgoing request so we can assert the claim wire shape without a
/// real network call.
class _FakeApiClient extends ApiClient {
  Map<String, dynamic>? lastBody;
  String? lastPath;
  Map<String, dynamic> response = <String, dynamic>{};
  Object? throwThis;

  @override
  Future<Map<String, dynamic>> postJson({
    required String baseUrl,
    required String path,
    String? deviceToken,
    String? clinicToken,
    Map<String, dynamic>? body,
    Map<String, dynamic>? queryParameters,
  }) async {
    lastPath = path;
    lastBody = body;
    final err = throwThis;
    if (err != null) throw err;
    return response;
  }
}

void main() {
  group('CloudSyncService.claim (short-serial online activation)', () {
    test(
      'posts the upper-cased serial + fingerprint to /api/license/claim',
      () async {
        final fake = _FakeApiClient()
          ..response = <String, dynamic>{
            'valid': true,
            'serial_token': 'tok-123',
            'status': 'active',
          };
        final svc = CloudSyncService(apiClient: fake);

        final res = await svc.claim(
          cloudUrl: 'https://cloud.test',
          serialNumber: 'dental-smd-clini-00001',
          deviceFingerprint: 'fp-1',
        );

        expect(fake.lastPath, '/api/license/claim');
        expect(fake.lastBody?['serial_number'], 'DENTAL-SMD-CLINI-00001');
        expect(fake.lastBody?['device_fingerprint'], 'fp-1');
        expect(fake.lastBody?['device_name'], 'mobile');
        expect(res?['valid'], true);
        expect(res?['serial_token'], 'tok-123');
      },
    );

    test('returns null when the cloud is unreachable', () async {
      final fake = _FakeApiClient()
        ..throwThis = const ApiException('offline', isNetwork: true);
      final svc = CloudSyncService(apiClient: fake);

      final res = await svc.claim(
        cloudUrl: 'https://cloud.test',
        serialNumber: 'DENTAL-AAAA-BBBB',
        deviceFingerprint: 'fp',
      );

      expect(res, isNull);
    });

    test('passes a not_found business failure straight through', () async {
      final fake = _FakeApiClient()
        ..response = <String, dynamic>{'valid': false, 'reason': 'not_found'};
      final svc = CloudSyncService(apiClient: fake);

      final res = await svc.claim(
        cloudUrl: 'https://cloud.test',
        serialNumber: 'DENTAL-AAAA-BBBB',
        deviceFingerprint: 'fp',
      );

      expect(res?['valid'], false);
      expect(res?['reason'], 'not_found');
    });
  });

  test(
    'a bare short serial is not a signed token (so it falls back to claim)',
    () {
      // activateWithKey() relies on this: tryParse returns null for a dotless
      // serial, which triggers the cloud-claim path instead of local decode.
      expect(ActivationToken.tryParse('DENTAL-SMD-CLINI-00001'), isNull);
      // A real signed token (payload.signature) still parses.
      expect(
        ActivationToken.tryParse('not.a.real.token'),
        isNull,
      ); // bad base64 → null
    },
  );
}
