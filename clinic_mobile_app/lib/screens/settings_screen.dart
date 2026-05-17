import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../config/app_config.dart';
import '../state/app_state.dart';
import '../services/clinic_api.dart' show SyncLink;
import '../services/connectivity_sync_service.dart';
import '../services/cloud_sync_service.dart';
// flutter_bluetooth_serial imported in Task 14 for peer picker
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
  late TextEditingController _cloudUrlCtrl;
  late TextEditingController _cloudSerialCtrl;
  late TextEditingController _cloudClinicNameCtrl;
  bool _syncing = false;
  bool _btScanning = false;
  bool _pairingCloud = false;
  String? _lastSync;
  String? _btStatus;
  String? _cloudStatus;

  @override
  void initState() {
    super.initState();
    final state = context.read<AppState>();
    _urlCtrl = TextEditingController(text: state.api.baseUrl);
    _cloudUrlCtrl = TextEditingController(
        text: state.cloudUrl ?? CloudSyncService.defaultCloudUrl);
    _cloudSerialCtrl = TextEditingController();
    _cloudClinicNameCtrl = TextEditingController(text: state.clinicName);
    _loadLastSync();
  }

  @override
  void dispose() {
    _urlCtrl.dispose();
    _cloudUrlCtrl.dispose();
    _cloudSerialCtrl.dispose();
    _cloudClinicNameCtrl.dispose();
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
    final app = context.read<AppState>();
    final mac = app.btBondedMac;
    if (mac == null || mac.isEmpty) {
      setState(() { _btScanning = false; _btStatus = 'No device bonded — pick one below'; });
      return;
    }
    setState(() { _btScanning = true; _btStatus = 'Connecting via Bluetooth…'; });
    final ok = await app.sync.syncViaBluetooth(mac);
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

  Future<void> _pairCloud() async {
    final url = _cloudUrlCtrl.text.trim();
    final serial = _cloudSerialCtrl.text.trim();
    final name = _cloudClinicNameCtrl.text.trim();
    if (url.isEmpty || serial.isEmpty || name.isEmpty) {
      setState(() => _cloudStatus =
          'Cloud URL, serial, and clinic name are all required.');
      return;
    }
    setState(() {
      _pairingCloud = true;
      _cloudStatus = 'Pairing with cloud…';
    });
    try {
      final info = await context
          .read<AppState>()
          .pairCloud(cloudUrl: url, serialNumber: serial, clinicName: name);
      if (!mounted) return;
      setState(() => _cloudStatus = info.alreadyRegistered
          ? 'Re-linked to existing cloud account.'
          : 'Cloud account created · clinic #${info.clinicId ?? '?'}.');
      _cloudSerialCtrl.clear();
      await _loadLastSync();
    } catch (e) {
      if (!mounted) return;
      setState(() => _cloudStatus = 'Pairing failed: $e');
    } finally {
      if (mounted) setState(() => _pairingCloud = false);
    }
  }

  Future<void> _unpairCloud() async {
    await context.read<AppState>().unpairCloud();
    if (!mounted) return;
    setState(() => _cloudStatus = 'Unpaired from cloud.');
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

          // ── Cloud Account ──────────────────────────────────────────────
          SectionHeader(title: 'Cloud Account'),
          ClinicCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  state.hasCloudAccount
                      ? 'Paired with ${state.cloudUrl ?? '—'}'
                      : 'Add a cloud account to sync this device when off the clinic Wi-Fi.',
                  style: TextStyle(
                      color: scheme.onSurfaceVariant, fontSize: 13, height: 1.4),
                ),
                if (!state.hasCloudAccount) ...[
                  const SizedBox(height: 12),
                  TextField(
                    controller: _cloudUrlCtrl,
                    decoration: const InputDecoration(
                      labelText: 'Cloud server URL',
                      prefixIcon: Icon(Icons.cloud_outlined),
                      hintText: 'https://app.dentacare.tech',
                    ),
                    keyboardType: TextInputType.url,
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _cloudSerialCtrl,
                    decoration: const InputDecoration(
                      labelText: 'Serial number',
                      prefixIcon: Icon(Icons.confirmation_number_outlined),
                      hintText: 'XXXX-XXXX-XXXX-XXXX',
                    ),
                    autocorrect: false,
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _cloudClinicNameCtrl,
                    decoration: const InputDecoration(
                      labelText: 'Clinic name',
                      prefixIcon: Icon(Icons.local_hospital_outlined),
                    ),
                  ),
                  const SizedBox(height: 12),
                  GradientButton(
                    label: _pairingCloud ? 'Pairing…' : 'Pair with cloud',
                    icon: Icons.cloud_sync_outlined,
                    loading: _pairingCloud,
                    onPressed: _pairingCloud ? null : _pairCloud,
                    width: double.infinity,
                  ),
                ] else ...[
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: _unpairCloud,
                    icon: const Icon(Icons.link_off),
                    label: const Text('Unpair from cloud'),
                  ),
                ],
                if (_cloudStatus != null) ...[
                  const SizedBox(height: 8),
                  Text(_cloudStatus!,
                      style: TextStyle(
                          fontSize: 12, color: scheme.onSurfaceVariant)),
                ],
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
                    final linkLabel =
                        _linkLabel(state.sync.activeLink);
                    final fullLabel = (status == SyncStatus.synced &&
                            linkLabel != null)
                        ? '$label · $linkLabel'
                        : label;
                    return Row(
                      children: [
                        Icon(icon, color: color, size: 18),
                        const SizedBox(width: 8),
                        Text(fullLabel,
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
                OutlinedButton.icon(
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
                  label: Text(_btScanning ? 'Connecting…' : 'Sync via Bluetooth',
                      style: const TextStyle(fontWeight: FontWeight.w700)),
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

  String? _linkLabel(SyncLink link) {
    switch (link) {
      case SyncLink.localWifi:
        return 'Local Wi-Fi';
      case SyncLink.cloud:
        return 'Cloud';
      case SyncLink.bluetooth:
        return 'Bluetooth';
      case SyncLink.none:
        return null;
    }
  }
}
