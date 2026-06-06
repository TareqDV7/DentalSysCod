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
