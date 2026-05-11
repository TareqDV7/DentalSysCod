import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../config/app_config.dart';
import '../state/app_state.dart';
import '../services/connectivity_sync_service.dart';
import '../services/bluetooth_sync_service.dart';
import '../widgets/gradient_button.dart';
import '../widgets/clinic_card.dart';
import '../widgets/section_header.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late TextEditingController _urlCtrl;
  bool _syncing = false;
  bool _btScanning = false;
  String? _lastSync;
  String? _btStatus;

  @override
  void initState() {
    super.initState();
    final state = context.read<AppState>();
    _urlCtrl = TextEditingController(text: state.api.baseUrl);
    _loadLastSync();
  }

  @override
  void dispose() {
    _urlCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadLastSync() async {
    final t = await context.read<AppState>().sync.getLastSyncTime();
    if (mounted) setState(() => _lastSync = t);
  }

  Future<void> _syncNow() async {
    setState(() => _syncing = true);
    await context.read<AppState>().sync.syncNow();
    await _loadLastSync();
    if (mounted) setState(() => _syncing = false);
  }

  Future<void> _bluetoothSync() async {
    setState(() { _btScanning = true; _btStatus = 'Scanning for nearby devices…'; });
    final ok = await context.read<AppState>().sync.syncViaBluetooth();
    if (mounted) {
      setState(() {
        _btScanning = false;
        _btStatus = ok
            ? 'Sync complete!'
            : context.read<AppState>().sync.statusMessage ?? 'Failed';
      });
    }
  }

  Future<void> _saveUrl() async {
    final url = _urlCtrl.text.trim();
    if (url.isEmpty) return;
    await context.read<AppState>().updateServerUrl(url);
    if (mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Server URL saved')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Appearance ──────���──────────────────────────────────────────
          SectionHeader(title: 'Appearance'),
          ClinicCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.language),
                  title: const Text('Language'),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _langBtn('EN', 'en', state),
                      const SizedBox(width: 6),
                      _langBtn('ع', 'ar', state),
                    ],
                  ),
                ),
                Divider(height: 1, color: scheme.outlineVariant),
                SwitchListTile(
                  secondary: const Icon(Icons.dark_mode_outlined),
                  title: const Text('Dark Mode'),
                  value: state.themeMode == ThemeMode.dark,
                  onChanged: (v) => state.setThemeMode(
                      v ? ThemeMode.dark : ThemeMode.light),
                  activeThumbColor: scheme.primary,
                ),
              ],
            ),
          ),

          const SizedBox(height: 20),

          // ── Server ────────────────────────────────────────────────���────
          SectionHeader(title: 'Server Connection'),
          ClinicCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextField(
                  controller: _urlCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Backend Server URL',
                    hintText: 'http://192.168.1.x:5000',
                    prefixIcon: Icon(Icons.link),
                  ),
                  keyboardType: TextInputType.url,
                ),
                const SizedBox(height: 12),
                GradientButton(
                  label: 'Save URL',
                  icon: Icons.save_outlined,
                  onPressed: _saveUrl,
                  width: double.infinity,
                ),
              ],
            ),
          ),

          const SizedBox(height: 20),

          // ── Sync ──────────────────────────────────────────────────────��
          SectionHeader(title: 'Data Sync'),
          ClinicCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Status indicator
                StreamBuilder<SyncStatus>(
                  stream: state.sync.statusStream,
                  initialData: state.sync.status,
                  builder: (context, snap) {
                    final status = snap.data ?? SyncStatus.idle;
                    final (icon, color, label) = _statusInfo(status);
                    return Row(
                      children: [
                        Icon(icon, color: color, size: 18),
                        const SizedBox(width: 8),
                        Text(label,
                            style:
                                TextStyle(color: color, fontWeight: FontWeight.w600)),
                      ],
                    );
                  },
                ),
                if (_lastSync != null) ...[
                  const SizedBox(height: 4),
                  Text('Last sync: $_lastSync',
                      style: TextStyle(
                          color: scheme.onSurfaceVariant, fontSize: 12)),
                ],
                const SizedBox(height: 14),
                GradientButton(
                  label: _syncing ? 'Syncing…' : 'Sync Now',
                  icon: Icons.sync,
                  loading: _syncing,
                  onPressed: _syncing ? null : _syncNow,
                  width: double.infinity,
                ),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // ── Bluetooth ──────────────────────────────────────────────────
          ClinicCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1D7FB7).withAlpha(25),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: const Icon(Icons.bluetooth,
                          color: Color(0xFF1D7FB7), size: 20),
                    ),
                    const SizedBox(width: 12),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Bluetooth Sync',
                              style: TextStyle(fontWeight: FontWeight.w700)),
                          Text('Sync with nearby devices when offline',
                              style:
                                  TextStyle(fontSize: 12, color: Color(0xFF627386))),
                        ],
                      ),
                    ),
                  ],
                ),
                if (_btStatus != null) ...[
                  const SizedBox(height: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: scheme.secondaryContainer,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(_btStatus!,
                        style: TextStyle(
                            fontSize: 12,
                            color: scheme.onSecondaryContainer)),
                  ),
                ],
                const SizedBox(height: 14),
                StreamBuilder<BluetoothSyncState>(
                  stream: state.sync
                      // ignore: invalid_use_of_protected_member
                      .statusStream
                      .map((_) => BluetoothSyncState.idle),
                  builder: (_, _) => OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size.fromHeight(44),
                      side: BorderSide(color: scheme.primary),
                      foregroundColor: scheme.primary,
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14)),
                    ),
                    onPressed: _btScanning ? null : _bluetoothSync,
                    icon: _btScanning
                        ? SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: scheme.primary))
                        : const Icon(Icons.bluetooth_searching),
                    label: Text(_btScanning ? 'Scanning…' : 'Find via Bluetooth',
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 20),

          // ── About ───────────────────────────────────────────────────────
          SectionHeader(title: 'About'),
          ClinicCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                ListTile(
                  leading: Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(
                        colors: [Color(0xFF0F6D7B), Color(0xFF1D7FB7)],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Icon(Icons.local_hospital,
                        color: Colors.white, size: 18),
                  ),
                  title: Text(AppBranding.systemName),
                  subtitle: Text(
                      '${AppBranding.clinicName} · v${AppBranding.appVersion}'),
                ),
                Divider(height: 1, color: scheme.outlineVariant),
                ListTile(
                  leading: const Icon(Icons.person_outline),
                  title: const Text('Doctor'),
                  subtitle: Text(AppBranding.doctorName),
                ),
                Divider(height: 1, color: scheme.outlineVariant),
                ListTile(
                  leading: const Icon(Icons.info_outline),
                  title: const Text('Offline-first with smart sync'),
                  subtitle: const Text('Internet sync · Bluetooth fallback'),
                ),
              ],
            ),
          ),

          const SizedBox(height: 32),
        ],
      ),
    );
  }

  Widget _langBtn(String label, String locale, AppState state) {
    final selected = state.locale == locale;
    return GestureDetector(
      onTap: () => state.setLocale(locale),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        decoration: BoxDecoration(
          color: selected
              ? const Color(0xFF0F6D7B)
              : Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
              color: selected
                  ? const Color(0xFF0F6D7B)
                  : Theme.of(context).colorScheme.outlineVariant),
        ),
        child: Text(label,
            style: TextStyle(
                color: selected ? Colors.white : null,
                fontWeight: FontWeight.w700)),
      ),
    );
  }

  (IconData, Color, String) _statusInfo(SyncStatus s) {
    switch (s) {
      case SyncStatus.syncing:
        return (Icons.sync, const Color(0xFF1D7FB7), 'Syncing…');
      case SyncStatus.synced:
        return (
            Icons.check_circle_outline, const Color(0xFF1F9A5F), 'Synced');
      case SyncStatus.offline:
        return (Icons.wifi_off, const Color(0xFFD89E1F), 'Offline');
      case SyncStatus.error:
        return (Icons.sync_problem, const Color(0xFFD9434E), 'Sync failed');
      default:
        return (
            Icons.sync_outlined, const Color(0xFF627386), 'Ready to sync');
    }
  }
}
