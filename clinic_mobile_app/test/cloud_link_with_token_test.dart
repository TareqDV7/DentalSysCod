import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/api_client.dart';
import 'package:clinic_mobile_app/services/cloud_sync_service.dart';

/// An ApiClient that records every HTTP call and refuses to perform any. If
/// [CloudSyncService.linkWithToken] ever reaches the network (e.g. by calling
/// /api/clinics/register), one of these throws and the test fails loudly.
class _NoNetworkApiClient extends ApiClient {
  final List<String> calls = [];

  @override
  Future<Map<String, dynamic>> postJson({
    required String baseUrl,
    required String path,
    String? deviceToken,
    String? clinicToken,
    Map<String, dynamic>? body,
    Map<String, dynamic>? queryParameters,
  }) async {
    calls.add('POST $path');
    throw StateError('linkWithToken must not perform any HTTP POST (got $path)');
  }

  @override
  Future<Map<String, dynamic>> getJson({
    required String baseUrl,
    required String path,
    String? deviceToken,
    String? clinicToken,
    Map<String, dynamic>? queryParameters,
  }) async {
    calls.add('GET $path');
    throw StateError('linkWithToken must not perform any HTTP GET (got $path)');
  }
}

void main() {
  group('CloudSyncService.linkWithToken', () {
    test('returns account info without calling register / any HTTP', () {
      final api = _NoNetworkApiClient();
      final service = CloudSyncService(apiClient: api);

      final info = service.linkWithToken(
        cloudUrl: 'https://app.dentacare.tech',
        clinicToken: 'TOK-xyz',
      );

      expect(info.clinicToken, 'TOK-xyz');
      expect(info.alreadyRegistered, isTrue);
      expect(info.clinicId, isNull);
      // The decisive assertion: no network was touched at all.
      expect(api.calls, isEmpty);
    });

    test('trims the token before returning it', () {
      final service = CloudSyncService(apiClient: _NoNetworkApiClient());
      final info = service.linkWithToken(
        cloudUrl: '  https://c.example  ',
        clinicToken: '  TOK-trim  ',
      );
      expect(info.clinicToken, 'TOK-trim');
    });

    test('throws ApiException on a blank cloud url', () {
      final service = CloudSyncService(apiClient: _NoNetworkApiClient());
      expect(
        () => service.linkWithToken(cloudUrl: '   ', clinicToken: 'tok'),
        throwsA(isA<ApiException>()),
      );
    });

    test('throws ApiException on a blank clinic token', () {
      final service = CloudSyncService(apiClient: _NoNetworkApiClient());
      expect(
        () => service.linkWithToken(
            cloudUrl: 'https://c.example', clinicToken: '  '),
        throwsA(isA<ApiException>()),
      );
    });
  });
}
