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

  /// GET an endpoint that returns a top-level JSON array (e.g. the
  /// medical-image listing). Kept separate from [getJson] which types the
  /// body as an object.
  Future<List<dynamic>> getJsonList({
    required String baseUrl,
    required String path,
    String? deviceToken,
    String? clinicToken,
    Map<String, dynamic>? queryParameters,
  }) async {
    try {
      final response = await _dio.get<List<dynamic>>(
        '${AppConfig.normalizeBaseUrl(baseUrl)}$path',
        queryParameters: queryParameters,
        options: _options(deviceToken, clinicToken),
      );
      return response.data ?? const <dynamic>[];
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

  /// Upload one file as multipart/form-data (used for medical images). dio
  /// sets the multipart boundary/content-type itself, so we must NOT force
  /// application/json here — only carry the auth header.
  Future<Map<String, dynamic>> postMultipart({
    required String baseUrl,
    required String path,
    String? deviceToken,
    String? clinicToken,
    required Map<String, String> fields,
    required String fileField,
    required String filePath,
    String? fileName,
  }) async {
    try {
      final form = FormData.fromMap({
        ...fields,
        fileField:
            await MultipartFile.fromFile(filePath, filename: fileName),
      });
      final response = await _dio.post<Map<String, dynamic>>(
        '${AppConfig.normalizeBaseUrl(baseUrl)}$path',
        data: form,
        options: _authOnlyOptions(deviceToken, clinicToken),
      );
      return response.data ?? <String, dynamic>{};
    } on DioException catch (error) {
      throw _toApiException(error);
    }
  }

  /// Download raw bytes (used to cache medical-image files locally).
  Future<List<int>> getBytes({
    required String baseUrl,
    required String path,
    String? deviceToken,
    String? clinicToken,
    Map<String, dynamic>? queryParameters,
  }) async {
    try {
      final response = await _dio.get<List<int>>(
        '${AppConfig.normalizeBaseUrl(baseUrl)}$path',
        queryParameters: queryParameters,
        options: _authOnlyOptions(deviceToken, clinicToken,
            responseType: ResponseType.bytes),
      );
      return response.data ?? const <int>[];
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

  /// Auth header only (no forced JSON content-type) — for multipart uploads
  /// and byte downloads where dio must control the content/response type.
  Options _authOnlyOptions(String? deviceToken, String? clinicToken,
      {ResponseType? responseType}) {
    final headers = <String, String>{};
    if (clinicToken != null && clinicToken.isNotEmpty) {
      headers['X-Clinic-Token'] = clinicToken;
    } else if (deviceToken != null && deviceToken.isNotEmpty) {
      headers['X-Device-Token'] = deviceToken;
    }
    return Options(headers: headers, responseType: responseType);
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
