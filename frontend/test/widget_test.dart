import 'package:flutter_test/flutter_test.dart';

import 'package:soulpulse/main.dart';

void main() {
  testWidgets('App renders login page', (WidgetTester tester) async {
    await tester.pumpWidget(const SoulPulseApp());
    expect(find.text('SoulPulse'), findsOneWidget);
  });
}
