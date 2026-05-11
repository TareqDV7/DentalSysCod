import 'api_client.dart';

class LicenseService {
  final ApiClient _api = ApiClient();

  Future<Map<String, dynamic>> activate({
    required String baseUrl,
    required String serialNumber,
    required String clinicName,
    required String deviceId,
    required String deviceName,
  }) {
    return _api.postJson(
      baseUrl: baseUrl,
      path: '/api/license/activate',
      body: <String, dynamic>{
        'serial_number': serialNumber,
        'clinic_name': clinicName,
        'device_id': deviceId,
        'device_name': deviceName,
      },
    );
  }

  Future<Map<String, dynamic>> status({required String baseUrl}) {
    return _api.getJson(baseUrl: baseUrl, path: '/api/license/status');
  }
}
