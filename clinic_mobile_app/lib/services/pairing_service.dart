import 'api_client.dart';

class PairingStartResponse {
  PairingStartResponse({required this.pairCode, required this.expiresAt});

  final String pairCode;
  final String? expiresAt;
}

class PairingCompleteResponse {
  PairingCompleteResponse({required this.deviceToken});

  final String deviceToken;
}

class PairingService {
  final ApiClient _api = ApiClient();

  Future<PairingStartResponse> startPairing({
    required String baseUrl,
    required String deviceName,
  }) async {
    final data = await _api.postJson(
      baseUrl: baseUrl,
      path: '/api/pairing/start',
      body: <String, dynamic>{'device_name': deviceName},
    );
    return PairingStartResponse(
      pairCode: (data['pair_code'] ?? '').toString(),
      expiresAt: data['expires_at']?.toString(),
    );
  }

  Future<PairingCompleteResponse> completePairing({
    required String baseUrl,
    required String pairCode,
    required String deviceId,
    required String deviceName,
  }) async {
    final data = await _api.postJson(
      baseUrl: baseUrl,
      path: '/api/pairing/complete',
      body: <String, dynamic>{
        'pair_code': pairCode,
        'device_id': deviceId,
        'device_name': deviceName,
      },
    );
    final token = (data['device_token'] ?? '').toString();
    if (token.isEmpty) {
      throw Exception('Pairing succeeded but no device token was returned.');
    }
    return PairingCompleteResponse(deviceToken: token);
  }
}
