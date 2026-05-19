import 'dart:async';

import 'package:flutter/material.dart';
import '../services/clinic_api.dart';
import '../services/cloud_sync_service.dart';
import '../services/database_service.dart';
import '../services/patient_service.dart';
import '../services/appointment_service.dart';
import '../services/billing_service.dart';
import '../services/catalog_service.dart';
import '../services/report_service.dart';
import '../services/internet_sync_service.dart';
import '../services/bluetooth_permissions.dart';
import '../services/bluetooth_sync_service.dart';
import '../services/background_sync_service.dart';
import '../services/connectivity_sync_service.dart';
import '../services/device_service.dart';
import '../services/local_storage_service.dart';

class AppState extends ChangeNotifier {
  final LocalStorageService _storage;

  late final ClinicApi api;
  late final DatabaseService db;
  late final CloudSyncService cloud;
  late final PatientService patients;
  late final AppointmentService appointments;
  late final BillingService billing;
  late final CatalogService catalog;
  late final ReportService reports;
  late final ConnectivitySyncService _connectivity;
  late final InternetSyncService _internet;
  late final BluetoothSyncService _bluetooth;
  late final BackgroundSyncService _bgSync;

  ConnectivitySyncService get sync => _connectivity;

  String _clinicName = 'Clinic';
  String _locale = 'en';
  ThemeMode _themeMode = ThemeMode.light;
  String? _cloudUrl;
  bool _hasCloudAccount = false;

  AppState(this._storage) {
    db = DatabaseService.instance;
    api = ClinicApi();
    cloud = CloudSyncService();
    patients = PatientService(db, api);
    appointments = AppointmentService(db, api);
    billing = BillingService(db, api);
    catalog = CatalogService(db, api);
    reports = ReportService(db, api);
    _internet = InternetSyncService(db, api);
    final deviceService = DeviceService();
    _bluetooth = BluetoothSyncService.production(
      deviceTokenLoader: _storage.getDeviceToken,
      // BT auto-pair: first sync attempt with no token sends op:bt_pair over
      // the already-OS-bonded BT channel; server issues a fresh device_token
      // and we persist it here. No 6-digit code dance required for BT.
      deviceTokenSaver: _storage.setDeviceToken,
      deviceIdLoader: deviceService.getDeviceId,
      // Incremental cursor — same key the HTTP pull writes, so a BT cycle
      // that follows an HTTP pull (or vice versa) only fetches what changed.
      // A null cursor here would re-pull the entire database every 30 s and
      // could clobber unpushed local edits with stale server rows.
      sinceLoader: () => db.getSyncMeta('last_sync_cursor'),
      onExport: (exported) async {
        await _internet.applyExportedDelta(exported);
      },
      buildPushPayload: _internet.buildPushPayload,
      onPushAcked: (payload) async {
        await _internet.markPayloadAsSynced(payload);
      },
      clientVersion: '1.0.0',
    );
    _connectivity = ConnectivitySyncService(
      internet: _internet,
      bluetooth: _bluetooth,
      storage: _storage,
      api: api,
      cloud: cloud,
    );
    _bgSync = BackgroundSyncService.production();
  }

  String get clinicName => _clinicName;
  String get locale => _locale;
  ThemeMode get themeMode => _themeMode;
  bool get isArabic => _locale == 'ar';
  String? get cloudUrl => _cloudUrl;
  bool get hasCloudAccount => _hasCloudAccount;

  // ── Bluetooth peer ───────────────────────────────────────────────────────
  bool _btEnabled = false;
  String? _btBondedMac;
  String? _btBondedLabel;
  String? _btLastSyncAt;
  String? _btLastError;

  bool get btEnabled => _btEnabled;
  String? get btBondedMac => _btBondedMac;
  String? get btBondedLabel => _btBondedLabel;
  String? get btLastSyncAt => _btLastSyncAt;
  String? get btLastError => _btLastError;

  Future<void> _loadBtState() async {
    _btEnabled = await _storage.getBtEnabled();
    _btBondedMac = await _storage.getBtBondedMac();
    _btBondedLabel = await _storage.getBtBondedLabel();
    _btLastSyncAt = await _storage.getBtLastSyncAt();
    _btLastError = await _storage.getBtLastError();
    notifyListeners();
  }

  Future<void> setBtEnabled(bool enabled) async {
    if (enabled) {
      // Android 12+ runtime perms — without these, every BT call fails
      // silently. Must be called from a foreground activity, which is
      // where this toggle lives.
      final granted = await BluetoothPermissions.ensureGranted();
      if (!granted) {
        _btEnabled = false;
        _btLastError = 'Bluetooth permission denied';
        await _storage.setBtEnabled(false);
        await _storage.setBtLastError(_btLastError!);
        await _bgSync.stop();
        notifyListeners();
        return;
      }
      _btLastError = null;
      await _storage.clearBtLastError();
    }
    _btEnabled = enabled;
    await _storage.setBtEnabled(enabled);
    if (enabled && _btBondedMac != null && _btBondedMac!.isNotEmpty) {
      await _bgSync.start();
    } else {
      await _bgSync.stop();
    }
    notifyListeners();
  }

  Future<void> bindBtPeer({required String mac, required String label}) async {
    await _storage.setBtBondedPeer(mac: mac, label: label);
    _btBondedMac = mac;
    _btBondedLabel = label;
    if (_btEnabled) await _bgSync.start();
    notifyListeners();
  }

  Future<void> unbindBtPeer() async {
    await _bgSync.stop();
    await _storage.clearBtBondedPeer();
    _btBondedMac = null;
    _btBondedLabel = null;
    notifyListeners();
  }

  /// Force one Bluetooth sync cycle right now, bypassing the LAN/cloud
  /// reachability gate. Use for the explicit "Sync now via Bluetooth" button.
  /// Routes through the background sync isolate so we don't race with the
  /// 30s auto-loop running there.
  Future<bool> syncViaBluetoothNow() async {
    final mac = _btBondedMac;
    if (mac == null || mac.isEmpty) {
      _btLastError = 'No clinic PC paired';
      await _storage.setBtLastError(_btLastError!);
      notifyListeners();
      return false;
    }
    final granted = await BluetoothPermissions.ensureGranted();
    if (!granted) {
      _btLastError = 'Bluetooth permission denied';
      await _storage.setBtLastError(_btLastError!);
      notifyListeners();
      return false;
    }
    // Fire force_sync into the sync isolate and wait for the result.
    final completer = Completer<bool>();
    late StreamSubscription sub;
    sub = _bgSync.onSyncFinished.listen((payload) {
      sub.cancel();
      completer.complete(payload?['ok'] == true);
    });
    _bgSync.forceSync();
    final ok = await completer.future.timeout(
      const Duration(seconds: 30),
      onTimeout: () {
        sub.cancel();
        return false;
      },
    );
    await _loadBtState(); // pull updated lastSyncAt / lastError from storage
    return ok;
  }

  Future<void> init() async {
    final baseUrl = await _storage.getBaseUrl();
    final token = await _storage.getDeviceToken();
    final clinic = await _storage.getClinicName();
    final cloudUrl = await _storage.getCloudUrl();
    final clinicToken = await _storage.getCloudClinicToken();
    if (baseUrl != null) api.baseUrl = baseUrl;
    if (token != null) api.deviceToken = token;
    if (clinicToken != null) api.clinicToken = clinicToken;
    if (clinic != null) _clinicName = clinic;
    _cloudUrl = cloudUrl;
    _hasCloudAccount = (cloudUrl != null && cloudUrl.isNotEmpty) &&
        (clinicToken != null && clinicToken.isNotEmpty);
    notifyListeners();
    unawaited(sync.syncNow().catchError((error) {
      debugPrint('Initial sync failed: $error');
    }));
    // Load BT state and start the auto-fallback loop if a peer is bonded + enabled.
    await _loadBtState();
    if (_btEnabled && _btBondedMac != null && _btBondedMac!.isNotEmpty) {
      await _bgSync.start();
    }
  }

  void setLocale(String locale) {
    _locale = locale;
    notifyListeners();
  }

  void setThemeMode(ThemeMode mode) {
    _themeMode = mode;
    notifyListeners();
  }

  Future<void> updateServerUrl(String url) async {
    api.baseUrl = url;
    await _storage.setBaseUrl(url);
    await _storage.setLocalUrl(url);
    notifyListeners();
  }

  /// Register this device's clinic on the shared cloud node and remember the token
  /// so subsequent syncs can fall back to (or run against) the cloud.
  Future<CloudAccountInfo> pairCloud({
    required String cloudUrl,
    required String serialNumber,
    required String clinicName,
  }) async {
    final info = await cloud.register(
      cloudUrl: cloudUrl,
      serialNumber: serialNumber,
      clinicName: clinicName,
    );
    await _storage.setCloudAccount(
      cloudUrl: cloudUrl,
      clinicToken: info.clinicToken,
      clinicId: info.clinicId,
    );
    if (clinicName.trim().isNotEmpty) {
      await _storage.setClinicName(clinicName.trim());
      _clinicName = clinicName.trim();
    }
    _cloudUrl = cloudUrl;
    _hasCloudAccount = true;
    api.clinicToken = info.clinicToken;
    notifyListeners();
    // Try a sync right away against the new target.
    unawaited(sync.syncNow());
    return info;
  }

  Future<void> unpairCloud() async {
    await _storage.clearCloudAccount();
    api.clinicToken = null;
    _cloudUrl = null;
    _hasCloudAccount = false;
    notifyListeners();
  }

  @override
  void dispose() {
    _connectivity.dispose();
    super.dispose();
  }
}
