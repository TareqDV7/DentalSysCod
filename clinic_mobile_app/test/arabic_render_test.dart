import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:clinic_mobile_app/state/app_state.dart';
import 'package:clinic_mobile_app/services/local_storage_service.dart';
import 'package:clinic_mobile_app/widgets/status_badge.dart';

/// End-to-end-ish check that the catalog wiring actually flips a widget's text
/// between English and Arabic when AppState.locale changes — the bug M1 fixes
/// was that the toggle only changed direction/font, not the words.
void main() {
  Widget host(AppState state, Widget child) {
    return ChangeNotifierProvider<AppState>.value(
      value: state,
      child: MaterialApp(
        locale: state.isArabic ? const Locale('ar') : const Locale('en'),
        home: Scaffold(body: Center(child: child)),
      ),
    );
  }

  testWidgets('StatusBadge renders English then Arabic on locale flip',
      (tester) async {
    final state = AppState(LocalStorageService());
    addTearDown(state.dispose);

    await tester.pumpWidget(host(state, const StatusBadge('paid')));
    await tester.pump();
    expect(find.text('Paid'), findsOneWidget);
    expect(find.text('مدفوع'), findsNothing);

    state.setLocale('ar');
    await tester.pumpAndSettle();

    expect(find.text('مدفوع'), findsOneWidget);
    expect(find.text('Paid'), findsNothing);
  });
}
