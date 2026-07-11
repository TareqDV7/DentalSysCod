import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/report_service.dart';

// Pure-function test for the formula ReportService.computeProfit() uses --
// matches the desktop formula in dental_clinic.py's reports_summary()/
// reports_weekly() (see docs/superpowers/specs/2026-07-11-unified-gross-profit-design.md):
// gross_profit = (followup net charge + billing net charge) - lab_expense - expenses.
void main() {
  group('ReportService.computeProfit', () {
    test('follow-up charge minus lab expense, no billing or general expenses', () {
      final profit = ReportService.computeProfit(
        followupNetCharge: 250, // 300 price - 50 discount, computed by the caller
        billingNetCharge: 0,
        labExpense: 30,
        expenses: 0,
      );
      expect(profit, 220);
    });

    test('combines follow-up and billing net charges', () {
      final profit = ReportService.computeProfit(
        followupNetCharge: 250,
        billingNetCharge: 450,
        labExpense: 0,
        expenses: 0,
      );
      expect(profit, 700);
    });

    test('subtracts general expenses on top of lab expense', () {
      final profit = ReportService.computeProfit(
        followupNetCharge: 300,
        billingNetCharge: 0,
        labExpense: 0,
        expenses: 120,
      );
      expect(profit, 180);
    });

    test('can go negative when costs exceed charges', () {
      final profit = ReportService.computeProfit(
        followupNetCharge: 50,
        billingNetCharge: 0,
        labExpense: 30,
        expenses: 100,
      );
      expect(profit, -80);
    });
  });
}
