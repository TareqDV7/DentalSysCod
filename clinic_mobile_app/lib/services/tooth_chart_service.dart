import '../models/tooth_condition.dart';
import '../models/tooth_chart_entry.dart';
import 'clinic_api.dart';
import 'database_service.dart';

/// Parsed result of GET /api/patients/{id}/tooth-chart.
class ToothChart {
  final List<ToothCondition> conditions;
  final Map<String, ToothChartEntry> teeth;
  const ToothChart({required this.conditions, required this.teeth});
}

/// Pure transform of the chart response body — unit-tested directly.
ToothChart parseToothChart(Map<String, dynamic> body) {
  final conditions = ((body['conditions'] as List?) ?? const [])
      .map((c) => ToothCondition.fromJson(Map<String, dynamic>.from(c as Map)))
      .toList();
  final teethMap = <String, ToothChartEntry>{};
  ((body['teeth'] as Map?) ?? const {}).forEach((k, v) {
    teethMap['$k'] = ToothChartEntry.fromJson(
      '$k',
      Map<String, dynamic>.from(v as Map),
    );
  });
  return ToothChart(conditions: conditions, teeth: teethMap);
}

/// Local-first catalog + chart access. Mirrors CatalogService:
/// writes go to the server first; badges are server-computed so the chart GET
/// is the source of truth for them.
class ToothChartService {
  final ClinicApi _api;

  // ignore: avoid_unused_constructor_parameters
  ToothChartService(DatabaseService db, this._api);

  /// Patient chart with computed badges. Requires connectivity for badges;
  /// callers should handle the offline error and fall back to local rows.
  Future<ToothChart> getChart(int patientId) async {
    final resp = await _api.get('/api/patients/$patientId/tooth-chart');
    return parseToothChart(resp);
  }

  /// Replace a tooth's full condition set. Empty list clears the tooth.
  Future<void> setToothConditions(
    int patientId,
    String toothNo,
    List<({int conditionId, String? note})> conditions,
  ) async {
    await _api.post(
      '/api/patients/$patientId/tooth-chart',
      body: {
        'tooth_no': toothNo,
        'conditions': [
          for (final c in conditions)
            {'condition_id': c.conditionId, 'note': c.note},
        ],
      },
    );
  }

  Future<void> clearTooth(int patientId, String toothNo) async {
    await _api.delete('/api/patients/$patientId/tooth-chart/$toothNo');
  }

  // --- Catalog ---

  /// Fetches the active conditions (or all when [all] is true).
  Future<List<ToothCondition>> getConditions({bool all = false}) async {
    final resp = await _api.getList(
      '/api/tooth-conditions${all ? '?all=1' : ''}',
    );
    return resp
        .map(
          (c) => ToothCondition.fromJson(Map<String, dynamic>.from(c as Map)),
        )
        .toList();
  }

  Future<void> addCondition(ToothCondition c) =>
      _api.post('/api/tooth-conditions', body: c.toJson());

  Future<void> updateCondition(ToothCondition c) =>
      _api.put('/api/tooth-conditions/${c.id}', body: c.toJson());

  Future<void> deleteCondition(int id) =>
      _api.delete('/api/tooth-conditions/$id');
}
