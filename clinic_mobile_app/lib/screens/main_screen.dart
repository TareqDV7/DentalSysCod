import 'package:flutter/material.dart';
import '../config/app_config.dart';
import '../services/local_storage_service.dart';

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  final _storage = LocalStorageService();
  String _serial = '';
  String _clinic = '';

  @override
  void initState() {
    super.initState();
    _loadInfo();
  }

  Future<void> _loadInfo() async {
    final s = await _storage.getSerialNumber();
    final c = await _storage.getClinicName();
    setState(() {
      _serial = s ?? '';
      _clinic = c ?? '';
    });
  }

  Future<void> _logout() async {
    await _storage.setDeviceToken('');
    await _storage.setSerialNumber('');
    if (!mounted) return;
    Navigator.of(context).pushReplacementNamed('/');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_clinic.isNotEmpty ? _clinic : AppBranding.systemName),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: _logout,
            tooltip: 'Clear license and restart',
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('License: ${_serial.isNotEmpty ? _serial : "Not activated"}'),
            const SizedBox(height: 12),
            const Text('Welcome to the Clinic App - main functionality goes here.'),
            const SizedBox(height: 20),
            ElevatedButton(onPressed: () {}, child: const Text('Patients')),
            const SizedBox(height: 8),
            ElevatedButton(onPressed: () {}, child: const Text('Appointments')),
            const SizedBox(height: 8),
            ElevatedButton(onPressed: () {}, child: const Text('Billing')),
          ],
        ),
      ),
    );
  }
}
