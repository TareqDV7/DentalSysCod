import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:clinic_mobile_app/models/tooth_condition.dart';
import 'package:clinic_mobile_app/models/tooth_chart_entry.dart';
import 'package:clinic_mobile_app/screens/odontogram_view.dart';
import 'package:clinic_mobile_app/services/tooth_chart_service.dart';
import 'package:clinic_mobile_app/state/app_state.dart';
import 'package:clinic_mobile_app/services/local_storage_service.dart';

/// Fake ToothChartReader that returns a small chart without any I/O.
class _FakeReader implements ToothChartReader {
  static const _cond = ToothCondition(
    id: 1,
    name: 'Decay',
    nameAr: null,
    color: '#ef4444',
    sortOrder: 0,
  );
  static final _chart = ToothChart(
    conditions: [_cond],
    teeth: {
      '16': ToothChartEntry.fromJson('16', {
        'conditions': [
          {
            'condition_id': 1,
            'condition_name': 'Decay',
            'color': '#ef4444',
            'note': null,
          },
        ],
        'source': 'chart',
        'has_plan': true,
        'unpaid_balance': 0,
      }),
      '46': ToothChartEntry.fromJson('46', {
        'conditions': [],
        'source': 'legacy',
        'has_plan': false,
        'unpaid_balance': 200.0,
      }),
    },
  );

  @override
  Future<ToothChart> getChart(int patientId) async => _chart;

  @override
  Future<void> setToothConditions(
    int pid,
    String t,
    List<({int conditionId, String? note})> conditions,
  ) async {}

  @override
  Future<void> clearTooth(int pid, String t) async {}

  @override
  Future<List<ToothCondition>> getConditions({bool all = false}) async => [
    _cond,
  ];
}

Widget _wrap(Widget child) {
  return ChangeNotifierProvider<AppState>(
    create: (_) => AppState(LocalStorageService()),
    child: MaterialApp(home: Scaffold(body: child)),
  );
}

void main() {
  testWidgets('renders 32 tooth cells', (tester) async {
    await tester.pumpWidget(
      _wrap(OdontogramView(patientId: 1, reader: _FakeReader())),
    );
    // Pump once to kick initState + complete the Future.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    // 32 _ToothCell instances (16 upper + 16 lower) wrapped in GestureDetector
    final cells = tester.widgetList<GestureDetector>(
      find.byType(GestureDetector),
    );
    expect(cells.length, greaterThanOrEqualTo(32));
  });

  testWidgets('shows legend condition name', (tester) async {
    await tester.pumpWidget(
      _wrap(OdontogramView(patientId: 1, reader: _FakeReader())),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('Decay'), findsWidgets);
  });
}
