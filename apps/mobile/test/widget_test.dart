import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:pick_mobile/api_client.dart';
import 'package:pick_mobile/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

class FakeApi implements PickApi {
  @override
  Future<String> login(String email, String password) async => 'token';
  @override
  Future<String> register(String name, String email, String password) async =>
      'token';
  @override
  Future<Map<String, dynamic>> dashboard(String token) async => {
    'choice_score': 84,
    'savings_cents': 4900,
    'prevented_spend_cents': 12000,
    'points_balance': 42,
  };
  @override
  Future<Map<String, dynamic>> analyze(
    String token,
    String query,
    int budgetCents,
    int urgency,
    int fit,
  ) async => {
    'id': 1,
    'verdict': 'BUY',
    'score': 86,
    'evidence': ['Price is below typical.', 'Strong budget fit.'],
    'product': {
      'id': 1,
      'name': 'Focus Headphones',
      'current_price_cents': 12900,
    },
  };
  @override
  Future<int> purchase(
    String token,
    int productId,
    int decisionId,
    int priceCents,
  ) async => 1;
  @override
  Future<void> ratePurchase(
    String token,
    int purchaseId,
    int satisfaction,
  ) async {}
  @override
  Future<void> track(String token, int productId, int targetPriceCents) async {}
}

void main() {
  testWidgets('registers and shows the decision workspace', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(PickApp(api: FakeApi()));
    await tester.pumpAndSettle();
    expect(find.text('Buy better.\nRegret less.'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('name')), 'Picker');
    await tester.enterText(find.byKey(const Key('email')), 'pick@example.com');
    await tester.enterText(find.byKey(const Key('password')), 'password1');
    await tester.drag(find.byType(ListView), const Offset(0, -350));
    await tester.pump();
    await tester.tap(find.byKey(const Key('create-account')));
    await tester.pumpAndSettle();
    expect(find.text('Get your signal.'), findsOneWidget);
    expect(find.text('84'), findsOneWidget);
  });

  testWidgets('renders deterministic verdict evidence', (tester) async {
    SharedPreferences.setMockInitialValues({'pick_token': 'token'});
    await tester.pumpWidget(PickApp(api: FakeApi()));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('product-query')),
      'headphones',
    );
    await tester.tap(find.byKey(const Key('analyze')));
    await tester.pumpAndSettle();
    expect(find.text('BUY'), findsOneWidget);
    expect(find.text('86 / 100'), findsOneWidget);
    expect(find.textContaining('Price is below typical.'), findsOneWidget);
  });
}
