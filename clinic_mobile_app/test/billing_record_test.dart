import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/models/billing_record.dart';

void main() {
  BillingRecord rec({required double subtotal, required double paid}) =>
      BillingRecord(patientId: 1, subtotal: subtotal, paidAmount: paid);

  group('BillingRecord money math', () {
    test('payment-only entry (charge 0, paid > 0) is Paid', () {
      final r = rec(subtotal: 0, paid: 200);
      expect(r.total, 0);
      expect(r.settled, 200);
      expect(r.balanceDue, 0);
      expect(r.statusLabel, 'Paid');
    });

    test('charge with no payment is Unpaid and owes the full amount', () {
      final r = rec(subtotal: 150, paid: 0);
      expect(r.total, 150);
      expect(r.balanceDue, 150);
      expect(r.statusLabel, 'Unpaid');
    });

    test('fully paid charge is Paid', () {
      expect(rec(subtotal: 100, paid: 100).statusLabel, 'Paid');
    });

    test('partly paid charge is Partial', () {
      final r = rec(subtotal: 100, paid: 40);
      expect(r.balanceDue, 60);
      expect(r.statusLabel, 'Partial');
    });

    test('discount reduces the total before settling', () {
      final r = BillingRecord(
          patientId: 1, subtotal: 100, discount: 20, paidAmount: 80);
      expect(r.total, 80);
      expect(r.balanceDue, 0);
      expect(r.statusLabel, 'Paid');
    });
  });
}
