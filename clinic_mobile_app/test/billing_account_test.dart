import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/models/billing_account.dart';

void main() {
  group('BillingAccount.status', () {
    BillingAccount account({required double total, required double paid}) =>
        BillingAccount(
          patientId: 1,
          patientName: 'Test Patient',
          total: total,
          paid: paid,
          balance: total - paid,
        );

    test('is unpaid when nothing has been paid', () {
      expect(account(total: 100, paid: 0).status, 'unpaid');
    });

    test('is partial when some but not all is paid', () {
      expect(account(total: 100, paid: 40).status, 'partial');
    });

    test('is paid when the full charged amount is settled', () {
      expect(account(total: 100, paid: 100).status, 'paid');
    });

    test('is paid when the patient is in credit (overpaid)', () {
      final a = account(total: 100, paid: 150);
      expect(a.status, 'paid');
      expect(a.balance, -50); // negative balance = credit held for the patient
    });

    test('is unpaid for a patient with charges and no payment', () {
      expect(account(total: 250, paid: 0).status, 'unpaid');
    });
  });

  group('BillingAccount.fromRow', () {
    test('parses a SQLite aggregate row, trimming the name', () {
      final a = BillingAccount.fromRow({
        'id': 7,
        'patient_name': '  Ahmad Saleh  ',
        'total': 300,
        'paid': 120.5,
        'balance': 179.5,
        'last_date': '2026-06-01',
        'line_count': 3,
      });

      expect(a.patientId, 7);
      expect(a.patientName, 'Ahmad Saleh');
      expect(a.total, 300.0);
      expect(a.paid, 120.5);
      expect(a.balance, 179.5);
      expect(a.lastDate, '2026-06-01');
      expect(a.lineCount, 3);
    });

    test('coerces string/int numerics and tolerates a null last_date', () {
      final a = BillingAccount.fromRow({
        'id': 2,
        'patient_name': 'No Date',
        'total': '50',
        'paid': 0,
        'balance': '50',
        'last_date': null,
      });

      expect(a.total, 50.0);
      expect(a.paid, 0.0);
      expect(a.lastDate, isNull);
      expect(a.lineCount, 0);
      expect(a.status, 'unpaid');
    });
  });
}
