import '../config/app_config.dart';
import 'api_client.dart';

class ServerRouterService {
  ServerRouterService({ApiClient? apiClient}) : _api = apiClient ?? ApiClient();

  final ApiClient _api;

  List<String> orderedCandidates({
    required String onlineUrl,
    required String localUrl,
    String? lastSuccessfulUrl,
  }) {
    final candidates = <String>[];

    void addCandidate(String? value) {
      final normalized = AppConfig.normalizeOrDefault(value, fallback: '');
      if (normalized.isEmpty || candidates.contains(normalized)) {
        return;
      }
      candidates.add(normalized);
    }

    addCandidate(lastSuccessfulUrl);
    addCandidate(onlineUrl);
    addCandidate(localUrl);
    return candidates;
  }

  Future<String> resolveWorkingBaseUrl({
    required String onlineUrl,
    required String localUrl,
    String? lastSuccessfulUrl,
  }) async {
    final candidates = orderedCandidates(
      onlineUrl: onlineUrl,
      localUrl: localUrl,
      lastSuccessfulUrl: lastSuccessfulUrl,
    );

    for (final candidate in candidates) {
      if (await _isReachable(candidate)) {
        return candidate;
      }
    }

    throw Exception('No clinic server is reachable.');
  }

  Future<bool> _isReachable(String baseUrl) async {
    try {
      await _api.getJson(baseUrl: baseUrl, path: '/api/system/readiness');
      return true;
    } catch (_) {
      return false;
    }
  }
}