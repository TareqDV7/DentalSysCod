import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/models/followup.dart';
import 'package:clinic_mobile_app/utils/patient_statement_pdf.dart';

Followup _f({
  double price = 0,
  double discount = 0,
  double payment = 0,
}) =>
    Followup(
      patientId: 1,
      followupDate: '2026-01-01',
      treatmentProcedure: 'x',
      price: price,
      discount: discount,
      payment: payment,
    );

void main() {
  group('PatientStatementPdf.computeTotals (desktop invoice-summary parity)', () {
    test('empty list → all zero', () {
      final t = PatientStatementPdf.computeTotals([]);
      expect(t.price, 0);
      expect(t.discount, 0);
      expect(t.toPay, 0);
      expect(t.paid, 0);
      expect(t.left, 0);
    });

    test('sums price/discount/paid across rows', () {
      final t = PatientStatementPdf.computeTotals([
        _f(price: 100, discount: 10, payment: 40),
        _f(price: 50, discount: 0, payment: 50),
      ]);
      expect(t.price, 150);
      expect(t.discount, 10);
      expect(t.paid, 90);
      // to_pay = 150 - 10 = 140; left = 140 - 90 = 50
      expect(t.toPay, 140);
      expect(t.left, 50);
    });

    test('to_pay clamps at 0 when discount exceeds price', () {
      final t = PatientStatementPdf.computeTotals([
        _f(price: 30, discount: 100, payment: 0),
      ]);
      expect(t.toPay, 0);
      expect(t.left, 0);
    });

    test('left clamps at 0 when overpaid (no negative balance on statement)', () {
      final t = PatientStatementPdf.computeTotals([
        _f(price: 100, discount: 0, payment: 130),
      ]);
      expect(t.toPay, 100);
      expect(t.paid, 130);
      expect(t.left, 0);
    });
  });
}
