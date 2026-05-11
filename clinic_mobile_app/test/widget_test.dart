import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:clinic_mobile_app/main.dart';

void main() {
  testWidgets('Bridge UI renders', (WidgetTester tester) async {
    await tester.pumpWidget(const ClinicMobileApp());
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });
}
