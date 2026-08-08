import 'dart:convert';
import 'package:http/http.dart' as http;

abstract class PickApi {
  Future<String> register(String name, String email, String password);
  Future<String> login(String email, String password);
  Future<Map<String, dynamic>> dashboard(String token);
  Future<Map<String, dynamic>> analyze(
    String token,
    String query,
    int budgetCents,
    int urgency,
    int fit,
  );
  Future<void> track(String token, int productId, int targetPriceCents);
  Future<int> purchase(
    String token,
    int productId,
    int decisionId,
    int priceCents,
  );
  Future<void> ratePurchase(String token, int purchaseId, int satisfaction);
}

class HttpPickApi implements PickApi {
  HttpPickApi({
    this.baseUrl = const String.fromEnvironment(
      'API_URL',
      defaultValue: 'http://10.0.2.2:8000',
    ),
  });
  final String baseUrl;

  Future<dynamic> _request(
    String path, {
    String? token,
    String method = 'GET',
    Object? body,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    final headers = {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
    final response = switch (method) {
      'POST' => await http.post(uri, headers: headers, body: jsonEncode(body)),
      'PATCH' => await http.patch(
        uri,
        headers: headers,
        body: jsonEncode(body),
      ),
      _ => await http.get(uri, headers: headers),
    };
    final decoded = response.body.isEmpty
        ? <String, dynamic>{}
        : jsonDecode(response.body);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception(
        decoded is Map
            ? decoded['detail'] ?? 'Request failed'
            : 'Request failed',
      );
    }
    return decoded;
  }

  @override
  Future<String> register(String name, String email, String password) async {
    final result = await _request(
      '/auth/register',
      method: 'POST',
      body: {'name': name, 'email': email, 'password': password},
    );
    return result['access_token'] as String;
  }

  @override
  Future<String> login(String email, String password) async {
    final result = await _request(
      '/auth/login',
      method: 'POST',
      body: {'email': email, 'password': password},
    );
    return result['access_token'] as String;
  }

  @override
  Future<Map<String, dynamic>> dashboard(String token) async =>
      Map<String, dynamic>.from(await _request('/dashboard', token: token));

  @override
  Future<Map<String, dynamic>> analyze(
    String token,
    String query,
    int budgetCents,
    int urgency,
    int fit,
  ) async => Map<String, dynamic>.from(
    await _request(
      '/decisions/analyze',
      token: token,
      method: 'POST',
      body: {
        'query': query,
        'budget_cents': budgetCents,
        'urgency': urgency,
        'fit': fit,
      },
    ),
  );

  @override
  Future<void> track(String token, int productId, int targetPriceCents) async =>
      _request(
        '/price-watches',
        token: token,
        method: 'POST',
        body: {'product_id': productId, 'target_price_cents': targetPriceCents},
      );

  @override
  Future<int> purchase(
    String token,
    int productId,
    int decisionId,
    int priceCents,
  ) async {
    final result = await _request(
      '/purchases',
      token: token,
      method: 'POST',
      body: {
        'product_id': productId,
        'decision_id': decisionId,
        'price_paid_cents': priceCents,
      },
    );
    return result['id'] as int;
  }

  @override
  Future<void> ratePurchase(
    String token,
    int purchaseId,
    int satisfaction,
  ) async => _request(
    '/purchases/$purchaseId',
    token: token,
    method: 'PATCH',
    body: {'satisfaction': satisfaction},
  );
}
