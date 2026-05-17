import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/models/followup.dart';

// Matches the server's `_recompute_followup_balances` — see
// docs/superpowers/specs/2026-05-17-mobile-followups-design.md. If these tests
// drift, the local cache and server canonical values will too.
void main() {
  ({double price, double discount, double payment}) row(
      double price, double discount, double payment) {
    return (price: price, discount: discount, payment: payment);
  }

  group('Followup.runningBalances', () {
    test('empty input → empty output', () {
      expect(Followup.runningBalances(const []), isEmpty);
    });

    test('single entry: paid in full → 0', () {
      // 100 charged, 100 paid → ledger zero
      expect(Followup.runningBalances([row(100, 0, 100)]), [0]);
    });

    test('single entry: partial pay → owed', () {
      expect(Followup.runningBalances([row(100, 0, 40)]), [60]);
    });

    test('single entry: overpayment → negative (patient credit)', () {
      expect(Followup.runningBalances([row(50, 0, 200)]), [-150]);
    });

    test('discount reduces the balance', () {
      expect(Followup.runningBalances([row(100, 30, 0)]), [70]);
    });

    test('multi-row cumulative walk', () {
      // 100 → bal 100
      // +50 entry, 25 discount, 0 paid → +25, bal 125
      // +0 entry, 0 discount, 80 paid (a payment row) → -80, bal 45
      expect(
        Followup.runningBalances([
          row(100, 0, 0),
          row(50, 25, 0),
          row(0, 0, 80),
        ]),
        [100, 125, 45],
      );
    });

    test('rounding: half-cent rounds half-up at 2 decimals', () {
      // 33.333 + 33.333 + 33.333 = 99.999 → 100.00 after rounding the cumulative
      expect(
        Followup.runningBalances([
          row(33.333, 0, 0),
          row(33.333, 0, 0),
          row(33.333, 0, 0),
        ]),
        [33.33, 66.67, 100.0],
      );
    });

    test('caller is responsible for ordering — different order, different balances', () {
      // If a row is moved earlier by date, the running balance for *every*
      // following row changes. This test pins that callers MUST sort by
      // (followup_date, id) before calling.
      final ascending =
          Followup.runningBalances([row(100, 0, 0), row(50, 0, 200)]);
      final reversed =
          Followup.runningBalances([row(50, 0, 200), row(100, 0, 0)]);
      expect(ascending, [100, -50]);
      expect(reversed, [-150, -50]); // final balance same, intermediate differs
    });
  });
}
