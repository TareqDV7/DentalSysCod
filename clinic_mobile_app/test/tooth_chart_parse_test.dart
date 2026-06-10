import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/tooth_chart_service.dart';
import 'package:clinic_mobile_app/models/tooth_condition.dart';

void main() {
  group('parseToothChart', () {
    test('splits conditions and per-tooth entries', () {
      final result = parseToothChart({
        'conditions': [
          {
            'id': 1,
            'name': 'Healthy',
            'color': '#22c55e',
            'sort_order': 0,
            'active': 1,
          },
          {
            'id': 2,
            'name': 'Decay',
            'color': '#ef4444',
            'sort_order': 1,
            'active': 1,
          },
        ],
        'teeth': {
          '16': {
            'conditions': [
              {
                'condition_id': 2,
                'condition_name': 'Decay',
                'color': '#ef4444',
                'note': 'distal',
              },
            ],
            'source': 'chart',
            'has_plan': true,
            'unpaid_balance': 0,
          },
          '26': {
            'conditions': [],
            'source': 'legacy',
            'has_plan': false,
            'unpaid_balance': 200,
          },
        },
      });
      expect(result.conditions, isA<List<ToothCondition>>());
      expect(result.conditions.length, 2);
      expect(result.teeth['16']!.conditions.single.name, 'Decay');
      expect(result.teeth['16']!.hasPlan, true);
      expect(result.teeth['26']!.unpaidBalance, 200);
      expect(result.teeth['26']!.source, 'legacy');
      expect(result.teeth['26']!.conditions, isEmpty);
    });

    test('empty chart yields no teeth', () {
      final result = parseToothChart({'conditions': [], 'teeth': {}});
      expect(result.teeth, isEmpty);
    });
  });
}
