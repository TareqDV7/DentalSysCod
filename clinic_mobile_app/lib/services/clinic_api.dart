import 'api_client.dart';

/// How the app is currently reaching the server.
enum SyncLink { localWifi, cloud, bluetooth, none }

/// Thin wrapper around ApiClient that carries the live baseUrl plus whichever
/// credential the current target needs — a device token for a local/LAN server,
/// or a clinic token for the shared cloud node. Call [configure] before a sync
/// to point it at the resolved target.
class ClinicApi {
  final ApiClient _client = ApiClient();
  String baseUrl;
  String? deviceToken;
  String? clinicToken;
  SyncLink link;

  ClinicApi({
    this.baseUrl = 'http://127.0.0.1:5000',
    this.deviceToken,
    this.clinicToken,
    this.link = SyncLink.none,
  });

  void configure({
    required String baseUrl,
    String? deviceToken,
    String? clinicToken,
    SyncLink? link,
  }) {
    this.baseUrl = baseUrl;
    this.deviceToken = deviceToken;
    this.clinicToken = clinicToken;
    if (link != null) this.link = link;
  }

  bool get isCloud => clinicToken != null && clinicToken!.isNotEmpty;

  Future<Map<String, dynamic>> get(String path,
          {Map<String, dynamic>? query}) =>
      _client.getJson(
        baseUrl: baseUrl,
        path: path,
        deviceToken: deviceToken,
        clinicToken: clinicToken,
        queryParameters: query,
      );

  Future<Map<String, dynamic>> post(String path,
          {Map<String, dynamic>? body, Map<String, dynamic>? query}) =>
      _client.postJson(
        baseUrl: baseUrl,
        path: path,
        deviceToken: deviceToken,
        clinicToken: clinicToken,
        body: body,
        queryParameters: query,
      );

  Future<Map<String, dynamic>> put(String path,
          {Map<String, dynamic>? body, Map<String, dynamic>? query}) =>
      _client.putJson(
        baseUrl: baseUrl,
        path: path,
        deviceToken: deviceToken,
        clinicToken: clinicToken,
        body: body,
        queryParameters: query,
      );

  Future<void> delete(String path, {Map<String, dynamic>? query}) =>
      _client.deleteJson(
        baseUrl: baseUrl,
        path: path,
        deviceToken: deviceToken,
        clinicToken: clinicToken,
        queryParameters: query,
      );
}
