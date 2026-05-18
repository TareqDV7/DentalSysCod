import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../config/app_config.dart';
import '../services/device_service.dart';
import '../services/local_storage_service.dart';
import '../services/pairing_service.dart';
import '../state/app_state.dart';

class PairingScreen extends StatefulWidget {
  const PairingScreen({required this.onPaired, super.key});

  final Future<void> Function() onPaired;

  @override
  State<PairingScreen> createState() => _PairingScreenState();
}

class _PairingScreenState extends State<PairingScreen> {
  final _storage = LocalStorageService();
  final _deviceService = DeviceService();
  final _pairing = PairingService();
  final _serverUrlController = TextEditingController();
  final _pairCodeController = TextEditingController();

  String _deviceId = '';
  String _status = '';
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _initDeviceId();
    _initServerUrl();
  }

  Future<void> _initDeviceId() async {
    final id = await _deviceService.getDeviceId();
    if (!mounted) return;
    setState(() => _deviceId = id);
  }

  Future<void> _initServerUrl() async {
    final saved = await _storage.getBaseUrl();
    if (!mounted) return;
    setState(() {
      _serverUrlController.text = AppConfig.normalizeOrDefault(
        saved,
        fallback: AppConfig.defaultServerUrl,
      );
    });
  }

  Future<void> _pair() async {
    final pairCode = _pairCodeController.text.trim();
    if (pairCode.isEmpty) {
      setState(() => _status = 'Enter the 6-digit code shown on the clinic PC');
      return;
    }
    final baseUrl = AppConfig.normalizeOrDefault(
      _serverUrlController.text,
      fallback: AppConfig.defaultServerUrl,
    );
    setState(() {
      _busy = true;
      _status = 'Pairing…';
    });
    try {
      final resp = await _pairing.completePairing(
        baseUrl: baseUrl,
        pairCode: pairCode,
        deviceId: _deviceId,
        deviceName: _deviceId,
      );
      await _storage.setBaseUrl(baseUrl);
      await _storage.setLocalUrl(baseUrl);
      await _storage.setDeviceToken(resp.deviceToken);
      if (!mounted) return;
      setState(() => _status = 'Paired — loading clinic data…');
      await widget.onPaired();
    } catch (e) {
      if (!mounted) return;
      setState(() => _status = 'Pairing failed: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _serverUrlController.dispose();
    _pairCodeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isArabic = context.select<AppState, bool>((s) => s.isArabic);
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: Text(isArabic ? 'إقران الجهاز' : 'Pair this device'),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: scheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      isArabic ? 'كيفية الإقران' : 'How to pair',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    const SizedBox(height: 8),
                    Text(isArabic
                        ? '1) افتح بوابة العيادة من المتصفح على كمبيوتر العيادة.\n'
                            '2) اضغط "بدء الإقران" واحصل على رمز من 6 أرقام.\n'
                            '3) أدخل الرمز هنا قبل انتهاء صلاحيته.'
                        : '1) On the clinic PC, open the web portal in a browser.\n'
                            '2) Click "Start Pairing" to get a 6-digit code.\n'
                            '3) Enter the code here before it expires.'),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              Text(
                '${isArabic ? "معرّف الجهاز" : "Device ID"}: $_deviceId',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _serverUrlController,
                keyboardType: TextInputType.url,
                decoration: InputDecoration(
                  labelText: isArabic ? 'رابط خادم العيادة' : 'Clinic server URL',
                  hintText: 'http://192.168.1.20:5000',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _pairCodeController,
                keyboardType: TextInputType.number,
                maxLength: 6,
                decoration: InputDecoration(
                  labelText: isArabic ? 'رمز الإقران' : 'Pair code',
                  hintText: '123456',
                ),
              ),
              const SizedBox(height: 8),
              FilledButton.icon(
                onPressed: _busy ? null : _pair,
                icon: _busy
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.link),
                label: Text(isArabic ? 'إقران الآن' : 'Pair now'),
              ),
              const SizedBox(height: 12),
              if (_status.isNotEmpty)
                Text(_status, style: Theme.of(context).textTheme.bodyMedium),
            ],
          ),
        ),
      ),
    );
  }
}
