import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/models/tooth_condition.dart';
import 'package:clinic_mobile_app/models/tooth_chart_entry.dart';
import 'package:clinic_mobile_app/models/treatment_plan.dart';

void main() {
  group('ToothCondition', () {
    test('parses server JSON', () {
      final c = ToothCondition.fromJson({
        'id': 2,
        'name': 'Decay',
        'name_ar': 'تسوّس',
        'color': '#ef4444',
        'icon': null,
        'sort_order': 1,
        'active': 1,
      });
      expect(c.id, 2);
      expect(c.name, 'Decay');
      expect(c.nameAr, 'تسوّس');
      expect(c.color, '#ef4444');
      expect(c.sortOrder, 1);
      expect(c.active, true);
    });

    test('toJson uses snake_case server keys', () {
      const c = ToothCondition(
          id: 1,
          name: 'Veneer',
          nameAr: 'فينير',
          color: '#10b981',
          icon: null,
          sortOrder: 9,
          active: true);
      final j = c.toJson();
      expect(j['name'], 'Veneer');
      expect(j['name_ar'], 'فينير');
      expect(j['sort_order'], 9);
    });
  });

  group('ToothChartEntry', () {
    test('parses a marked tooth with computed badges', () {
      final e = ToothChartEntry.fromJson('16', {
        'condition_id': 2,
        'condition_name': 'Decay',
        'color': '#ef4444',
        'note': 'distal',
        'source': 'chart',
        'has_plan': true,
        'unpaid_balance': 150.0,
      });
      expect(e.toothNo, '16');
      expect(e.conditionId, 2);
      expect(e.conditionName, 'Decay');
      expect(e.color, '#ef4444');
      expect(e.hasPlan, true);
      expect(e.unpaidBalance, 150.0);
      expect(e.source, 'chart');
    });

    test('legacy tooth has null condition but may carry badges', () {
      final e = ToothChartEntry.fromJson('26', {
        'condition_id': null,
        'condition_name': null,
        'color': null,
        'note': null,
        'source': 'legacy',
        'has_plan': false,
        'unpaid_balance': 200.0,
      });
      expect(e.conditionId, isNull);
      expect(e.source, 'legacy');
      expect(e.unpaidBalance, 200.0);
    });
  });

  _planTests();
}

void _planTests() {
  group('TreatmentPlan.teeth', () {
    test('parses teeth array from server JSON', () {
      final p = TreatmentPlan.fromJson({
        'id': 1,
        'patient_id': 5,
        'plan_name': 'Upper crowns',
        'teeth': ['16', '26', '36'],
      });
      expect(p.teeth, ['16', '26', '36']);
    });

    test('defaults to empty teeth when absent', () {
      final p = TreatmentPlan.fromJson(
          {'id': 1, 'patient_id': 5, 'plan_name': 'X'});
      expect(p.teeth, isEmpty);
    });

    test('toJson includes teeth', () {
      final p = TreatmentPlan(patientId: 5, planName: 'X', teeth: const ['16']);
      expect(p.toJson()['teeth'], ['16']);
    });
  });
}
