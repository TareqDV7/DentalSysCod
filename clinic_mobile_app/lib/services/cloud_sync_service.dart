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
  Future<CloudAccountInfo> register({
    required String cloudUrl,
    required String serialNumber,
    required String clinicName,
  }) async {
    final data = await _api.postJson(
      baseUrl: AppConfig.normalizeBaseUrl(cloudUrl),
      path: '/api/clinics/register',
      body: <String, dynamic>{
        'serial_number': serialNumber.trim(),
        'clinic_name': clinicName.trim(),
      },
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

  /// Link this device to a clinic the desktop already registered, using a clinic
  /// token scanned from the desktop pairing QR. Unlike [register] this makes NO
  /// `/api/clinics/register` call — the token is all the cloud needs to select
  /// the tenant. Validates its inputs and returns the account info to persist.
  ///
  /// Throws [ApiException] if the url or token is blank/invalid.
  CloudAccountInfo linkWithToken({
    required String cloudUrl,
    required String clinicToken,
  }) {
    final url = cloudUrl.trim();
    final token = clinicToken.trim();
    if (url.isEmpty) {
      throw const ApiException('Cloud URL is required to link by token');
    }
    if (token.isEmpty) {
      throw const ApiException('Clinic token is required to link by token');
    }
    // The clinic id isn't carried in the QR — link-by-token doesn't need it.
    return CloudAccountInfo(
      clinicId: null,
      clinicToken: token,
      alreadyRegistered: true,
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
