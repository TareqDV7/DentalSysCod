import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_bluetooth_serial/flutter_bluetooth_serial.dart';
import '../config/app_config.dart';
import '../models/holiday.dart';
import '../state/app_state.dart';
import '../services/bluetooth_permissions.dart';
import '../services/clinic_api.dart' show SyncLink;
import '../services/connectivity_sync_service.dart';
import '../services/cloud_sync_service.dart';
import '../services/local_storage_service.dart';
import 'catalog_screen.dart';
import 'pairing_screen.dart';
import '../utils/app_strings.dart';
import '../utils/date_format_helper.dart';
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
  bool _pairingCloud = false;
  String? _lastSync;
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

  Future<void> _openPairingScreen() async {
    final app = context.read<AppState>();
    await Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => PairingScreen(onPaired: () async {
        // Re-init so api.deviceToken + sync targets pick up the fresh token.
        await app.init();
        if (mounted) Navigator.of(context).pop();
      }),
    ));
    await _loadLastSync();
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
                const SizedBox(height: 8),
                FutureBuilder<String?>(
                  future: LocalStorageService().getDeviceToken(),
                  builder: (context, snap) {
                    final hasToken =
                        snap.data != null && snap.data!.isNotEmpty;
                    final isArabic =
                        context.read<AppState>().locale == 'ar';
                    return OutlinedButton.icon(
                      onPressed: _openPairingScreen,
                      icon: Icon(
                          hasToken ? Icons.refresh : Icons.qr_code_2_outlined),
                      label: Text(hasToken
                          ? (isArabic
                              ? 'إعادة الإقران عبر الواي فاي (رمز)'
                              : 'Re-pair via Wi-Fi (code)')
                          : (isArabic
                              ? 'إقران عبر الواي فاي (رمز 6 أرقام)'
                              : 'Pair via Wi-Fi (6-digit code)')),
                    );
                  },
                ),
              ],
            ),
          ),

          const SizedBox(height: 20),

          // ── Bluetooth Peer ─────────────────────────────────────────────
          SectionHeader(title: 'Bluetooth peer'),
          ClinicCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Consumer<AppState>(
                  builder: (context, app, _) {
                    final hasError =
                        app.btLastError != null && app.btLastError!.isNotEmpty;
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SwitchListTile.adaptive(
                          contentPadding: EdgeInsets.zero,
                          value: app.btEnabled,
                          onChanged: (v) => app.setBtEnabled(v),
                          title: Text(app.locale == 'ar'
                              ? 'تفعيل المزامنة عبر بلوتوث'
                              : 'Enable Bluetooth sync'),
                        ),
                        const SizedBox(height: 8),
                        if (app.btBondedLabel != null)
                          ListTile(
                            contentPadding: EdgeInsets.zero,
                            leading: const Icon(Icons.devices_other_rounded),
                            title: Text(app.btBondedLabel!),
                            subtitle: Text(app.btBondedMac ?? ''),
                            trailing: TextButton(
                              onPressed: () => app.unbindBtPeer(),
                              child: Text(app.locale == 'ar' ? 'إزالة' : 'Remove'),
                            ),
                          )
                        else
                          GradientButton(
                            label: app.locale == 'ar' ? 'اختر كمبيوتر العيادة' : 'Pick clinic PC',
                            icon: Icons.bluetooth_searching_rounded,
                            onPressed: () => _pickBondedPeer(context, app),
                          ),
                        if (hasError) ...[
                          const SizedBox(height: 12),
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: const Color(0xFFFDE7E9),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: const Color(0xFFD9434E)),
                            ),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Icon(Icons.error_outline,
                                    color: Color(0xFF9C2E36), size: 18),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(app.btLastError!,
                                      style: const TextStyle(
                                          color: Color(0xFF9C2E36),
                                          fontSize: 13)),
                                ),
                              ],
                            ),
                          ),
                        ] else ...[
                          const SizedBox(height: 8),
                          Text(_btStatusLine(app),
                              style: Theme.of(context).textTheme.bodySmall),
                        ],
                        if (app.btBondedMac != null && app.btEnabled) ...[
                          const SizedBox(height: 12),
                          GradientButton(
                            label: app.locale == 'ar'
                                ? 'مزامنة الآن عبر بلوتوث'
                                : 'Sync now via Bluetooth',
                            icon: Icons.bluetooth_connected_rounded,
                            onPressed: () => _syncBtNow(context, app),
                            width: double.infinity,
                          ),
                        ],
                      ],
                    );
                  },
                ),
              ],
            ),
          ),

          const SizedBox(height: 20),

          // ── Procedure catalog ───────────────────────────────────────────
          SectionHeader(
              title: state.locale == 'ar'
                  ? 'كتالوج الإجراءات'
                  : 'Procedure catalog'),
          ClinicCard(
            padding: EdgeInsets.zero,
            child: ListTile(
              leading: const Icon(Icons.medical_services_outlined),
              title: Text(state.locale == 'ar'
                  ? 'إدارة الإجراءات والأسعار'
                  : 'Manage procedures & prices'),
              subtitle: Text(
                  state.locale == 'ar'
                      ? 'يستخدم في الإقتراحات داخل زيارة المريض'
                      : 'Used to prefill price/lab in follow-up entries',
                  style: TextStyle(
                      color: Theme.of(context)
                          .colorScheme
                          .onSurfaceVariant,
                      fontSize: 12)),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                      builder: (_) => const CatalogScreen())),
            ),
          ),

          const SizedBox(height: 20),

          // ── Holidays ────────────────────────────────────────────────────
          SectionHeader(
              title:
                  AppStrings.t('holidays', isArabic: state.locale == 'ar')),
          ClinicCard(child: _HolidaysSection()),

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

  String _btStatusLine(AppState app) {
    if (!app.btEnabled) return app.locale == 'ar' ? 'متوقّفة' : 'Disabled';
    if (app.btBondedMac == null) {
      return app.locale == 'ar' ? 'لم يتم الاقتران' : 'Not paired';
    }
    if (app.btLastError != null && app.btLastError!.isNotEmpty) {
      return '⚠️ ${app.btLastError}';
    }
    if (app.btLastSyncAt != null && app.btLastSyncAt!.isNotEmpty) {
      return (app.locale == 'ar' ? 'آخر مزامنة: ' : 'Last sync: ') +
          app.btLastSyncAt!;
    }
    return app.locale == 'ar' ? 'في انتظار الاقتراب…' : 'Waiting to come into range…';
  }

  Future<void> _syncBtNow(BuildContext context, AppState app) async {
    final messenger = ScaffoldMessenger.of(context);
    messenger.showSnackBar(SnackBar(
        duration: const Duration(seconds: 2),
        content: Text(app.locale == 'ar'
            ? 'محاولة المزامنة عبر بلوتوث…'
            : 'Trying Bluetooth sync…')));
    final ok = await app.syncViaBluetoothNow();
    if (!context.mounted) return;
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(SnackBar(
        backgroundColor:
            ok ? const Color(0xFF1F9A5F) : const Color(0xFFD9434E),
        content: Text(ok
            ? (app.locale == 'ar' ? 'تمت المزامنة عبر بلوتوث' : 'Synced via Bluetooth')
            : (app.locale == 'ar'
                ? 'فشل: ${app.btLastError ?? "غير معروف"}'
                : 'Failed: ${app.btLastError ?? "unknown"}'))));
    if (ok) await _loadLastSync();
  }

  Future<void> _pickBondedPeer(BuildContext context, AppState app) async {
    // Android 12+ runtime perms — getBondedDevices() returns empty without
    // BLUETOOTH_CONNECT granted, which is indistinguishable from "no devices
    // paired" to the user.
    final granted = await BluetoothPermissions.ensureGranted();
    if (!granted) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(
          app.locale == 'ar'
              ? 'يلزم منح إذن بلوتوث من إعدادات أندرويد'
              : 'Bluetooth permission denied — grant it in Android settings')));
      return;
    }
    final List<BluetoothDevice> devices;
    try {
      devices = await FlutterBluetoothSerial.instance.getBondedDevices();
    } catch (_) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(
          app.locale == 'ar'
              ? 'تعذّر الوصول إلى بلوتوث'
              : 'Could not access Bluetooth')));
      return;
    }
    if (!context.mounted) return;
    if (devices.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(
          app.locale == 'ar'
              ? 'لا توجد أجهزة مقترنة — اقترن أولًا من إعدادات بلوتوث'
              : 'No bonded devices — pair in Android Bluetooth settings first')));
      return;
    }
    final picked = await showModalBottomSheet<BluetoothDevice>(
      context: context,
      builder: (_) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            for (final d in devices)
              ListTile(
                leading: const Icon(Icons.computer_rounded),
                title: Text(d.name ?? d.address),
                subtitle: Text(d.address),
                onTap: () => Navigator.of(context).pop(d),
              ),
          ],
        ),
      ),
    );
    if (picked != null) {
      await app.bindBtPeer(mac: picked.address, label: picked.name ?? picked.address);
    }
  }
}

class _HolidaysSection extends StatefulWidget {
  const _HolidaysSection();
  @override
  State<_HolidaysSection> createState() => _HolidaysSectionState();
}

class _HolidaysSectionState extends State<_HolidaysSection> {
  List<Holiday> _holidays = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final db = context.read<AppState>().db;
    final rows = await db.getHolidays();
    if (mounted) setState(() { _holidays = rows; _loading = false; });
  }

  Future<void> _add() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime.now(),
      firstDate: DateTime(DateTime.now().year - 1),
      lastDate: DateTime.now().add(const Duration(days: 365 * 3)),
    );
    if (picked == null || !mounted) return;
    final nameCtrl = TextEditingController();
    final isArabic = context.read<AppState>().locale == 'ar';
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(AppStrings.t('add_holiday', isArabic: isArabic)),
        content: TextField(
          controller: nameCtrl,
          decoration: InputDecoration(
              labelText: AppStrings.t('holiday_name', isArabic: isArabic)),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: Text(AppStrings.t('cancel', isArabic: isArabic))),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: Text(AppStrings.t('save', isArabic: isArabic))),
        ],
      ),
    );
    nameCtrl.dispose();
    if (saved != true || !mounted) return;
    final state = context.read<AppState>();
    await state.db.upsertHoliday(Holiday(
      holidayDate: DateFormatHelper.formatDateForApi(picked),
      name: nameCtrl.text.trim().isEmpty ? null : nameCtrl.text.trim(),
      updatedAt: DateTime.now().toIso8601String(),
      isSynced: false,
    ));
    unawaited(state.sync.syncNow());
    await _load();
  }

  Future<void> _delete(Holiday h) async {
    if (h.id == null) return;
    final isArabic = context.read<AppState>().locale == 'ar';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(AppStrings.t('confirm_delete', isArabic: isArabic)),
        content: Text(
            AppStrings.t('delete_holiday_confirm', isArabic: isArabic)),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: Text(AppStrings.t('cancel', isArabic: isArabic))),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: Text(AppStrings.t('delete', isArabic: isArabic),
                  style: const TextStyle(color: Color(0xFFD9434E)))),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    final state = context.read<AppState>();
    await state.db.deleteHoliday(h.id!);
    unawaited(state.sync.syncNow());
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final isArabic = state.locale == 'ar';
    if (_loading) {
      return const SizedBox(
        height: 60,
        child: Center(child: CircularProgressIndicator()),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (_holidays.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Text(AppStrings.t('no_holidays', isArabic: isArabic),
                style: TextStyle(
                    color: Theme.of(context).colorScheme.onSurfaceVariant)),
          )
        else
          ..._holidays.map((h) => ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.event_busy_outlined),
                title: Text(h.holidayDate),
                subtitle: (h.name ?? '').isEmpty ? null : Text(h.name!),
                trailing: IconButton(
                  icon: const Icon(Icons.delete,
                      size: 18, color: Color(0xFFD9434E)),
                  onPressed: () => _delete(h),
                ),
              )),
        const SizedBox(height: 8),
        GradientButton(
          label: AppStrings.t('add_holiday', isArabic: isArabic),
          icon: Icons.add,
          onPressed: _add,
          width: double.infinity,
        ),
      ],
    );
  }
}

void unawaited(Future<void> f) {}
