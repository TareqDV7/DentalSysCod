import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/utils/amount_expr.dart';

void main() {
  group('AmountExpr.evaluate', () {
    test('plain number', () {
      expect(AmountExpr.evaluate('40'), 40);
      expect(AmountExpr.evaluate('40.5'), 40.5);
    });
    test('addition / subtraction', () {
      expect(AmountExpr.evaluate('20+20'), 40);
      expect(AmountExpr.evaluate('50 - 12.5'), 37.5);
    });
    test('precedence and parentheses', () {
      expect(AmountExpr.evaluate('2+3*4'), 14);
      expect(AmountExpr.evaluate('(2+3)*4'), 20);
    });
    test('leading minus is a negative number', () {
      expect(AmountExpr.evaluate('-5'), -5);
    });
    test('divide by zero is invalid', () {
      expect(AmountExpr.evaluate('10/0'), isNull);
    });
    test('illegal characters / names rejected', () {
      expect(AmountExpr.evaluate('20+a'), isNull);
      expect(AmountExpr.evaluate('__import__'), isNull);
      expect(AmountExpr.evaluate(''), isNull);
    });
    test('malformed expression rejected', () {
      expect(AmountExpr.evaluate('20+'), isNull);
      expect(AmountExpr.evaluate('(2+3'), isNull);
      expect(AmountExpr.evaluate('2 3'), isNull);
    });
    test('over length cap rejected', () {
      expect(AmountExpr.evaluate('1${'+1' * 25}'), isNull);
    });
  });

  group('AmountExpr.exprIfMeaningful', () {
    test('keeps real expressions verbatim', () {
      expect(AmountExpr.exprIfMeaningful('20+20'), '20+20');
      expect(AmountExpr.exprIfMeaningful('  100-30  '), '100-30');
      expect(AmountExpr.exprIfMeaningful('3*4'), '3*4');
    });
    test('drops bare numbers and lone negatives', () {
      expect(AmountExpr.exprIfMeaningful('40'), isNull);
      expect(AmountExpr.exprIfMeaningful('-5'), isNull);
    });
    test('drops invalid input', () {
      expect(AmountExpr.exprIfMeaningful('20+x'), isNull);
    });
  });

  group('AmountExpr.parse', () {
    test('expression yields value + stored expr', () {
      final r = AmountExpr.parse('20+20');
      expect(r.value, 40);
      expect(r.expr, '20+20');
    });
    test('plain number yields value, no expr', () {
      final r = AmountExpr.parse('40');
      expect(r.value, 40);
      expect(r.expr, isNull);
    });
    test('blank yields zero, no expr', () {
      final r = AmountExpr.parse('');
      expect(r.value, 0);
      expect(r.expr, isNull);
    });
  });
}
