// clinic_mobile_app/test/license_gate_service_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/license_gate_service.dart';

void main() {
  group('mapGateState', () {
    test('maps active', () {
      expect(mapGateState({'state': 'active'}), isA<GateActive>());
    });
    test('maps grace with date', () {
      final s = mapGateState({'state': 'grace', 'grace_until': '2027-06-17'});
      expect(s, isA<GateGrace>());
      expect((s as GateGrace).graceUntil, '2027-06-17');
    });
    test('maps view_only', () {
      expect(mapGateState({'state': 'view_only'}), isA<GateViewOnly>());
    });
    test('maps unlicensed', () {
      expect(mapGateState({'state': 'unlicensed'}), isA<GateUnlicensed>());
    });
    test('unknown/missing → GateUnknown', () {
      expect(mapGateState({'state': 'wat'}), isA<GateUnknown>());
      expect(mapGateState({}), isA<GateUnknown>());
    });
  });
}
