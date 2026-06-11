import 'api_client.dart';
import '../config/app_config.dart';

class CloudAccountInfo {
  CloudAccountInfo({
    required this.clinicId,
    required this.clinicToken,
    required this.alreadyRegistered,
  });

  final int? clinicId;
  final String clinicToken;
  final bool alreadyRegistered;
}

/// Talks to the shared **cloud node** (`CLINIC_CLOUD_MODE=1`): registers this
/// clinic against a serial to obtain its clinic token, and answers reachability
/// checks used by the connectivity chooser (LAN local → cloud → Bluetooth).
class CloudSyncService {
  CloudSyncService({ApiClient? apiClient}) : _api = apiClient ?? ApiClient();

  final ApiClient _api;

  static const String defaultCloudUrl = 'https://app.dentacare.tech';

  /// Provision (or look up) this clinic on the cloud node. Idempotent per serial.
  /// [offlineToken] is the vendor-signed activation key — required so the cloud's
  /// Ed25519 signed-serial gate (`CLINIC_REQUIRE_SIGNED_SERIAL=1`) accepts the
  /// registration. Omitting it makes the cloud reject the call with HTTP 403.
  Future<CloudAccountInfo> register({
    required String cloudUrl,
    required String serialNumber,
    required String clinicName,
    String? offlineToken,
  }) async {
    final body = <String, dynamic>{
      'serial_number': serialNumber.trim(),
      'clinic_name': clinicName.trim(),
    };
    final offline = offlineToken?.trim() ?? '';
    if (offline.isNotEmpty) {
      body['offline_token'] = offline;
    }
    final data = await _api.postJson(
      baseUrl: AppConfig.normalizeBaseUrl(cloudUrl),
      path: '/api/clinics/register',
      body: body,
    );
    final token = (data['clinic_token'] ?? '').toString();
    if (token.isEmpty) {
      throw const ApiException('Cloud did not return a clinic token');
    }
    final id = data['clinic_id'];
    return CloudAccountInfo(
      clinicId: id is int ? id : int.tryParse('${id ?? ''}'),
      clinicToken: token,
      alreadyRegistered: data['already_registered'] == true,
    );
  }

  /// Short-serial online activation: ask the cloud for the cached signed token of
  /// [serialNumber] and claim a device slot. Returns the parsed cloud body — which
  /// carries `valid` and, on success, `serial_token` — or null when unreachable.
  /// Business failures come back as `{valid:false, reason:...}` (HTTP 200), not an
  /// exception, mirroring `/api/license/validate`.
  Future<Map<String, dynamic>?> claim({
    required String cloudUrl,
    required String serialNumber,
    required String deviceFingerprint,
    String deviceName = 'mobile',
  }) async {
    try {
      return await _api.postJson(
        baseUrl: AppConfig.normalizeBaseUrl(cloudUrl),
        path: '/api/license/claim',
        body: <String, dynamic>{
          'serial_number': serialNumber.trim().toUpperCase(),
          'device_fingerprint': deviceFingerprint,
          'device_name': deviceName,
        },
      );
    } on ApiException {
      return null;
    }
  }

  /// Is this URL serving the API right now? For the cloud node a clinic token is
  /// required on every `/api/*` call, so pass it when checking the cloud.
  Future<bool> isReachable(String url, {String? clinicToken}) async {
    if (url.trim().isEmpty) return false;
    try {
      await _api.getJson(
        baseUrl: AppConfig.normalizeBaseUrl(url),
        path: '/api/system/readiness',
        clinicToken: clinicToken,
      );
      return true;
    } catch (_) {
      return false;
    }
  }
}
