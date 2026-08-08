import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api_client.dart';

const ink = Color(0xFF16221D);
const paper = Color(0xFFF5F3EC);
const mint = Color(0xFFC9FF67);
const green = Color(0xFF1F5C42);

void main() => runApp(PickApp(api: HttpPickApi()));

class PickApp extends StatefulWidget {
  const PickApp({super.key, required this.api});
  final PickApi api;
  @override
  State<PickApp> createState() => _PickAppState();
}

class _PickAppState extends State<PickApp> {
  String? token;
  bool ready = false;
  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    token = (await SharedPreferences.getInstance()).getString('pick_token');
    if (mounted) setState(() => ready = true);
  }

  Future<void> _signedIn(String value) async {
    await (await SharedPreferences.getInstance()).setString(
      'pick_token',
      value,
    );
    setState(() => token = value);
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    title: 'PICK',
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: green),
      scaffoldBackgroundColor: paper,
      fontFamily: 'sans',
      inputDecorationTheme: const InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(),
      ),
    ),
    home: !ready
        ? const Scaffold(body: Center(child: CircularProgressIndicator()))
        : token == null
        ? AuthScreen(api: widget.api, onSignedIn: _signedIn)
        : HomeScreen(api: widget.api, token: token!),
  );
}

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key, required this.api, required this.onSignedIn});
  final PickApi api;
  final ValueChanged<String> onSignedIn;
  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final name = TextEditingController(),
      email = TextEditingController(),
      password = TextEditingController();
  bool loading = false, registerMode = true;
  String? error;
  Future<void> submit() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final auth = registerMode
          ? await widget.api.register(name.text, email.text, password.text)
          : await widget.api.login(email.text, password.text);
      widget.onSignedIn(auth);
    } catch (e) {
      setState(() => error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(28),
        children: [
          const Text(
            'PICK.',
            style: TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.w900,
              letterSpacing: -1,
            ),
          ),
          const SizedBox(height: 64),
          const Text(
            'DECISIONS THAT PAY OFF',
            style: TextStyle(
              color: green,
              fontSize: 11,
              fontWeight: FontWeight.bold,
              letterSpacing: 2,
            ),
          ),
          const SizedBox(height: 10),
          const Text(
            'Buy better.\nRegret less.',
            style: TextStyle(
              fontSize: 53,
              height: .95,
              letterSpacing: -3,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(height: 22),
          const Text(
            'Independent verdicts, price protection, and rewards for every smart choice — including not buying.',
            style: TextStyle(fontSize: 16, height: 1.5),
          ),
          const SizedBox(height: 42),
          if (registerMode) ...[
            TextField(
              key: const Key('name'),
              controller: name,
              decoration: const InputDecoration(labelText: 'Name'),
            ),
            const SizedBox(height: 12),
          ],
          TextField(
            key: const Key('email'),
            controller: email,
            keyboardType: TextInputType.emailAddress,
            decoration: const InputDecoration(labelText: 'Email'),
          ),
          const SizedBox(height: 12),
          TextField(
            key: const Key('password'),
            controller: password,
            obscureText: true,
            decoration: const InputDecoration(
              labelText: 'Password (8+ characters)',
            ),
          ),
          if (error != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(error!, style: const TextStyle(color: Colors.red)),
            ),
          const SizedBox(height: 18),
          FilledButton(
            key: const Key('create-account'),
            onPressed: loading ? null : submit,
            style: FilledButton.styleFrom(
              backgroundColor: ink,
              padding: const EdgeInsets.all(18),
              shape: const RoundedRectangleBorder(
                borderRadius: BorderRadius.all(Radius.circular(4)),
              ),
            ),
            child: Text(loading ? 'Working…' : 'Create account'),
          ),
          TextButton(
            onPressed: () => setState(() {
              registerMode = !registerMode;
              error = null;
            }),
            child: Text(
              registerMode
                  ? 'Already a member? Sign in'
                  : 'New to PICK? Create account',
            ),
          ),
          const SizedBox(height: 10),
          const Text(
            'Verdicts are never influenced by sponsors or affiliate revenue.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.black54, fontSize: 12),
          ),
        ],
      ),
    ),
  );
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.api, required this.token});
  final PickApi api;
  final String token;
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final query = TextEditingController(),
      budget = TextEditingController(text: '200');
  double urgency = 5, fit = 7, satisfaction = 8;
  bool loading = false;
  Map<String, dynamic>? result, metrics;
  String? message;
  int? purchaseId;
  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    try {
      final data = await widget.api.dashboard(widget.token);
      if (mounted) setState(() => metrics = data);
    } catch (_) {}
  }

  Future<void> analyze() async {
    if (query.text.trim().length < 2) return;
    setState(() {
      loading = true;
      message = null;
    });
    try {
      final data = await widget.api.analyze(
        widget.token,
        query.text.trim(),
        (double.parse(budget.text) * 100).round(),
        urgency.round(),
        fit.round(),
      );
      setState(() => result = data);
      await _refresh();
    } catch (e) {
      setState(() => message = e.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> act() async {
    final product = Map<String, dynamic>.from(result!['product']);
    if (result!['verdict'] == 'BUY') {
      purchaseId = await widget.api.purchase(
        widget.token,
        product['id'],
        result!['id'],
        product['current_price_cents'],
      );
      setState(
        () => message = 'Purchase protected. Tell us how it feels below.',
      );
    } else {
      await widget.api.track(
        widget.token,
        product['id'],
        (product['current_price_cents'] * .9).round(),
      );
      setState(() => message = 'Tracking a 10% price drop.');
    }
    await _refresh();
  }

  Future<void> rate() async {
    if (purchaseId == null) return;
    await widget.api.ratePurchase(
      widget.token,
      purchaseId!,
      satisfaction.round(),
    );
    setState(() => message = 'Choice Score updated from your satisfaction.');
    await _refresh();
  }

  String dollars(num cents) => '\$${(cents / 100).toStringAsFixed(2)}';
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      backgroundColor: paper,
      title: const Text('PICK.', style: TextStyle(fontWeight: FontWeight.w900)),
      actions: [
        IconButton(onPressed: _refresh, icon: const Icon(Icons.refresh)),
      ],
    ),
    body: ListView(
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 60),
      children: [
        const Text(
          'SHOULD YOU BUY IT?',
          style: TextStyle(
            color: green,
            fontSize: 11,
            fontWeight: FontWeight.bold,
            letterSpacing: 2,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Get your signal.',
          style: TextStyle(
            fontSize: 39,
            fontWeight: FontWeight.w900,
            letterSpacing: -2,
          ),
        ),
        const SizedBox(height: 22),
        Container(
          padding: const EdgeInsets.all(18),
          color: Colors.white,
          child: Column(
            children: [
              TextField(
                key: const Key('product-query'),
                controller: query,
                decoration: const InputDecoration(
                  labelText: 'Product URL or search',
                  hintText: 'Wireless headphones',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: budget,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Budget (USD)'),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  const SizedBox(width: 75, child: Text('Urgency')),
                  Expanded(
                    child: Slider(
                      value: urgency,
                      min: 1,
                      max: 10,
                      divisions: 9,
                      label: urgency.round().toString(),
                      onChanged: (v) => setState(() => urgency = v),
                    ),
                  ),
                ],
              ),
              Row(
                children: [
                  const SizedBox(width: 75, child: Text('Fit')),
                  Expanded(
                    child: Slider(
                      value: fit,
                      min: 1,
                      max: 10,
                      divisions: 9,
                      label: fit.round().toString(),
                      onChanged: (v) => setState(() => fit = v),
                    ),
                  ),
                ],
              ),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  key: const Key('analyze'),
                  onPressed: loading ? null : analyze,
                  style: FilledButton.styleFrom(
                    backgroundColor: ink,
                    padding: const EdgeInsets.all(16),
                  ),
                  child: Text(
                    loading ? 'Weighing evidence…' : 'Get my verdict →',
                  ),
                ),
              ),
            ],
          ),
        ),
        if (message != null)
          Padding(
            padding: const EdgeInsets.only(top: 16),
            child: Text(
              message!,
              style: const TextStyle(color: green, fontWeight: FontWeight.bold),
            ),
          ),
        if (result != null) VerdictCard(result: result!, onAction: act),
        if (purchaseId != null)
          Container(
            margin: const EdgeInsets.only(top: 14),
            padding: const EdgeInsets.all(16),
            color: mint,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'HOW DID IT FEEL?',
                  style: TextStyle(
                    fontWeight: FontWeight.w900,
                    letterSpacing: 1,
                  ),
                ),
                Slider(
                  value: satisfaction,
                  min: 1,
                  max: 10,
                  divisions: 9,
                  label: satisfaction.round().toString(),
                  onChanged: (v) => setState(() => satisfaction = v),
                ),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: rate,
                    style: FilledButton.styleFrom(backgroundColor: ink),
                    child: const Text('Update my Choice Score'),
                  ),
                ),
              ],
            ),
          ),
        const SizedBox(height: 28),
        GridView.count(
          crossAxisCount: 2,
          childAspectRatio: 1.25,
          crossAxisSpacing: 10,
          mainAxisSpacing: 10,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          children: [
            MetricCard(
              label: 'Choice Score',
              value: '${metrics?['choice_score'] ?? '—'}',
              accent: true,
            ),
            MetricCard(
              label: 'Saved',
              value: dollars(metrics?['savings_cents'] ?? 0),
            ),
            MetricCard(
              label: 'Prevented',
              value: dollars(metrics?['prevented_spend_cents'] ?? 0),
            ),
            MetricCard(
              label: 'Points',
              value: '${metrics?['points_balance'] ?? 0}',
            ),
          ],
        ),
        const SizedBox(height: 22),
        const Text(
          'WAIT and PASS choices can earn more than BUY. Spending is never required.',
          style: TextStyle(color: Colors.black54, fontSize: 12),
        ),
      ],
    ),
  );
}

class VerdictCard extends StatelessWidget {
  const VerdictCard({super.key, required this.result, required this.onAction});
  final Map<String, dynamic> result;
  final VoidCallback onAction;
  @override
  Widget build(BuildContext context) {
    final verdict = result['verdict'];
    final product = result['product'];
    final color = verdict == 'BUY'
        ? green
        : verdict == 'WAIT'
        ? const Color(0xFFC18B12)
        : const Color(0xFF8E5549);
    return Container(
      margin: const EdgeInsets.only(top: 24),
      decoration: BoxDecoration(
        border: Border.all(color: color, width: 2),
        color: Colors.white,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.all(20),
            color: color,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  verdict,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 2,
                  ),
                ),
                Text(
                  '${result['score']} / 100',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 24,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  product['name'],
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 14),
                ...List<String>.from(result['evidence']).map(
                  (item) => Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Text('✓  $item'),
                  ),
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: onAction,
                    style: FilledButton.styleFrom(backgroundColor: ink),
                    child: Text(
                      verdict == 'BUY' ? 'I bought it' : 'Track this price',
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class MetricCard extends StatelessWidget {
  const MetricCard({
    super.key,
    required this.label,
    required this.value,
    this.accent = false,
  });
  final String label, value;
  final bool accent;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(18),
    color: accent ? mint : ink,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: TextStyle(color: accent ? ink : Colors.white70)),
        Text(
          value,
          style: TextStyle(
            color: accent ? ink : Colors.white,
            fontSize: 25,
            fontWeight: FontWeight.w900,
          ),
        ),
      ],
    ),
  );
}
