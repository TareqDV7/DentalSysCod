import 'api_client.dart';

/// Thin wrapper around ApiClient that carries the live baseUrl + deviceToken
/// so every service can call it without repeating those params.
class ClinicApi {
  final ApiClient _client = ApiClient();
  String baseUrl;
  String? deviceToken;

  ClinicApi({this.baseUrl = 'http://127.0.0.1:5000', this.deviceToken});

  Future<Map<String, dynamic>> get(String path,
      {Map<String, dynamic>? query}) =>
      _client.getJson(
        baseUrl: baseUrl,
        path: path,
        deviceToken: deviceToken,
        queryParameters: query,
      );

  Future<Map<String, dynamic>> post(String path,
      {Map<String, dynamic>? body, Map<String, dynamic>? query}) =>
      _client.postJson(
        baseUrl: baseUrl,
        path: path,
        deviceToken: deviceToken,
        body: body,
        queryParameters: query,
      );

  Future<Map<String, dynamic>> put(String path,
      {Map<String, dynamic>? body, Map<String, dynamic>? query}) =>
      _client.putJson(
        baseUrl: baseUrl,
        path: path,
        deviceToken: deviceToken,
        body: body,
        queryParameters: query,
      );

  Future<void> delete(String path, {Map<String, dynamic>? query}) =>
      _client.deleteJson(
        baseUrl: baseUrl,
        path: path,
        deviceToken: deviceToken,
        queryParameters: query,
      );
}
