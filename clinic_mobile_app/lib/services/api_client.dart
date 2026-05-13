import 'package:dio/dio.dart';

import '../config/app_config.dart';

class ApiException implements Exception {
  final String message;
  final int? statusCode;
  final bool isNetwork;

  const ApiException(
    this.message, {
    this.statusCode,
    this.isNetwork = false,
  });

  @override
  String toString() => message;
}

class ApiClient {
  final Dio _dio = Dio(
    BaseOptions(
      connectTimeout: const Duration(seconds: 12),
      receiveTimeout: const Duration(seconds: 20),
      sendTimeout: const Duration(seconds: 20),
      receiveDataWhenStatusError: true,
    ),
  );

  Future<Map<String, dynamic>> getJson({
    required String baseUrl,
    required String path,
    String? deviceToken,
    String? clinicToken,
    Map<String, dynamic>? queryParameters,
  }) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '${AppConfig.normalizeBaseUrl(baseUrl)}$path',
        queryParameters: queryParameters,
        options: _options(deviceToken, clinicToken),
      );
      return response.data ?? <String, dynamic>{};
    } on DioException catch (error) {
      throw _toApiException(error);
    }
  }

  Future<Map<String, dynamic>> postJson({
    required String baseUrl,
    required String path,
    String? deviceToken,
    String? clinicToken,
    Map<String, dynamic>? body,
    Map<String, dynamic>? queryParameters,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '${AppConfig.normalizeBaseUrl(baseUrl)}$path',
        data: body,
        queryParameters: queryParameters,
        options: _options(deviceToken, clinicToken),
      );
      return response.data ?? <String, dynamic>{};
    } on DioException catch (error) {
      throw _toApiException(error);
    }
  }

  Future<Map<String, dynamic>> putJson({
    required String baseUrl,
    required String path,
    String? deviceToken,
    String? clinicToken,
    Map<String, dynamic>? body,
    Map<String, dynamic>? queryParameters,
  }) async {
    try {
      final response = await _dio.put<Map<String, dynamic>>(
        '${AppConfig.normalizeBaseUrl(baseUrl)}$path',
        data: body,
        queryParameters: queryParameters,
        options: _options(deviceToken, clinicToken),
      );
      return response.data ?? <String, dynamic>{};
    } on DioException catch (error) {
      throw _toApiException(error);
    }
  }

  Future<void> deleteJson({
    required String baseUrl,
    required String path,
    String? deviceToken,
    String? clinicToken,
    Map<String, dynamic>? queryParameters,
  }) async {
    try {
      await _dio.delete<Map<String, dynamic>>(
        '${AppConfig.normalizeBaseUrl(baseUrl)}$path',
        queryParameters: queryParameters,
        options: _options(deviceToken, clinicToken),
      );
    } on DioException catch (error) {
      throw _toApiException(error);
    }
  }

  Options _options(String? deviceToken, [String? clinicToken]) {
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (clinicToken != null && clinicToken.isNotEmpty) {
      // Cloud node: the clinic token both authenticates and selects the tenant DB.
      headers['X-Clinic-Token'] = clinicToken;
    } else if (deviceToken != null && deviceToken.isNotEmpty) {
      headers['X-Device-Token'] = deviceToken;
    }
    return Options(headers: headers);
  }

  String _extractError(DioException error) {
    final response = error.response;
    final data = response?.data;
    if (data is Map && data['error'] != null) {
      return data['error'].toString();
    }
    if (data is String && data.trim().isNotEmpty) {
      return data.trim();
    }
    final statusCode = response?.statusCode;
    if (statusCode != null) {
      return 'Request failed ($statusCode)';
    }
    return error.message ?? 'Network request failed';
  }

  ApiException _toApiException(DioException error) {
    final statusCode = error.response?.statusCode;
    final isNetwork = statusCode == null;
    return ApiException(
      _extractError(error),
      statusCode: statusCode,
      isNetwork: isNetwork,
    );
  }
}
