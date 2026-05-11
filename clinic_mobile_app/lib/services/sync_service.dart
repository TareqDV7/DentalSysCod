import 'api_client.dart';

class SyncService {
  final ApiClient _api = ApiClient();

  Future<Map<String, dynamic>> readiness({required String baseUrl}) {
    return _api.getJson(baseUrl: baseUrl, path: '/api/system/readiness');
  }

  Future<Map<String, dynamic>> exportSnapshot({
    required String baseUrl,
    required String deviceToken,
  }) {
    return _api.getJson(
      baseUrl: baseUrl,
      path: '/api/sync/export',
      deviceToken: deviceToken,
    );
  }

  Future<Map<String, dynamic>> importSnapshot({
    required String baseUrl,
    required String deviceToken,
    required Map<String, dynamic> snapshotPayload,
  }) {
    return _api.postJson(
      baseUrl: baseUrl,
      path: '/api/sync/import',
      deviceToken: deviceToken,
      body: snapshotPayload,
    );
  }
}
