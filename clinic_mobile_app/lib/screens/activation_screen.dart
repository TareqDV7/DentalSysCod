import 'package:flutter/material.dart';
import '../config/app_config.dart';
import '../services/local_storage_service.dart';
import '../services/device_service.dart';
import '../services/license_service.dart';

class ActivationScreen extends StatefulWidget {
  final VoidCallback onActivated;
  const ActivationScreen({required this.onActivated, super.key});

  @override
  State<ActivationScreen> createState() => _ActivationScreenState();
}

class _ActivationScreenState extends State<ActivationScreen> {
  final _serialController = TextEditingController();
  final _clinicController = TextEditingController();
  final _serverUrlController = TextEditingController();
  final _tokenController = TextEditingController();
  final _storage = LocalStorageService();
  final _deviceService = DeviceService();
  final _licenseService = LicenseService();

  bool _busy = false;
  String _deviceId = '';
  String _status = '';

  @override
  void initState() {
    super.initState();
    _initDeviceId();
    _initServerUrl();
  }

  Future<void> _initDeviceId() async {
    final id = await _deviceService.getDeviceId();
    setState(() => _deviceId = id);
  }

  Future<void> _initServerUrl() async {
    final saved = await _storage.getBaseUrl();
    setState(() {
      _serverUrlController.text = AppConfig.normalizeOrDefault(
        saved,
        fallback: AppConfig.defaultServerUrl,
      );
    });
  }

  Future<void> _activate() async {
    setState(() {
      _busy = true;
      _status = 'Activating...';
    });

    final baseUrl = AppConfig.normalizeOrDefault(
      _serverUrlController.text,
      fallback: AppConfig.defaultServerUrl,
    );
    try {
      await _storage.setBaseUrl(baseUrl);
      final resp = await _licenseService.activate(
        baseUrl: baseUrl,
        serialNumber: _serialController.text.trim(),
        clinicName: _clinicController.text.trim(),
        deviceId: _deviceId,
        deviceName: _deviceId,
      );

      final token = resp['offline_license_token'] ?? resp['offline_token'] ?? resp['token'];
      if (token != null) {
        await _storage.setDeviceToken(token as String);
        await _storage.setSerialNumber(_serialController.text.trim());
        await _storage.setClinicName(_clinicController.text.trim());
        setState(() => _status = 'Activation successful');
        widget.onActivated();
        return;
      }
      setState(() => _status = 'Activation failed: no token');
    } catch (e) {
      setState(() => _status = 'Activation error: $e');
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _useToken() async {
    final token = _tokenController.text.trim();
    if (token.isEmpty) {
      setState(() => _status = 'No token provided');
      return;
    }
    setState(() {
      _busy = true;
      _status = 'Applying token...';
    });
    try {
      await _storage.setDeviceToken(token);
      // Optionally store serial/clinic if provided
      final serial = _serialController.text.trim();
      final clinic = _clinicController.text.trim();
      if (serial.isNotEmpty) await _storage.setSerialNumber(serial);
      if (clinic.isNotEmpty) await _storage.setClinicName(clinic);
      setState(() => _status = 'Token applied');
      widget.onActivated();
      return;
    } catch (e) {
      setState(() => _status = 'Error applying token: $e');
    } finally {
      setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _serialController.dispose();
    _clinicController.dispose();
    _serverUrlController.dispose();
    _tokenController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Activate License')),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const SizedBox(height: 8),
            Text('Device ID: $_deviceId'),
            const SizedBox(height: 16),
            TextField(
              controller: _serverUrlController,
              decoration: const InputDecoration(
                labelText: 'Server URL',
                hintText: 'http://192.168.1.81:5000',
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _serialController,
              decoration: const InputDecoration(labelText: 'Serial'),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _clinicController,
              decoration: const InputDecoration(labelText: 'Clinic Name (optional)'),
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _busy ? null : _activate,
              child: _busy ? const CircularProgressIndicator() : const Text('Activate'),
            ),
            const SizedBox(height: 12),
            const Divider(),
            const SizedBox(height: 12),
            TextField(
              controller: _tokenController,
              decoration: const InputDecoration(
                labelText: 'Paste offline token (optional)',
                hintText: 'eyJ...',
              ),
            ),
            const SizedBox(height: 8),
            ElevatedButton(
              onPressed: _busy ? null : _useToken,
              child: const Text('Use Token'),
            ),
            const SizedBox(height: 8),
            Text(_status),
          ],
        ),
      ),
    );
  }
}
