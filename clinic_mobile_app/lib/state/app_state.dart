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
import '../services/medical_image_service.dart';
import '../services/internet_sync_service.dart';
import '../services/bluetooth_permissions.dart';
import '../services/bluetooth_sync_service.dart';
import '../services/connectivity_sync_service.dart';
import '../services/device_service.dart';
import '../services/local_storage_service.dart';
import '../utils/bt_error_message.dart';

class AppState extends ChangeNotifier with WidgetsBindingObserver {
  final LocalStorageService _storage;

  late final ClinicApi api;
  late final DatabaseService db;
  late final CloudSyncService cloud;
  late final PatientService patients;
  late final AppointmentService appointments;
  late final BillingService billing;
  late final CatalogService catalog;
  late final ReportService reports;
  late final MedicalImageService medicalImages;
  late final ConnectivitySyncService _connectivity;
  late final InternetSyncService _internet;
  late final BluetoothSyncService _bluetooth;

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
    medicalImages = MedicalImageService(db, api);
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
    WidgetsBinding.instance.addObserver(this);
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
    final stored = await _storage.getBtLastError();
    _btLastError = _classifyStoredBtError(stored);
    notifyListeners();
  }

  /// Stored BT error strings are tokens, never rendered text — storing tokens
  /// (not pre-localized strings) lets [setLocale] re-render the active banner
  /// without waiting for the next BT cycle. Two token vocabularies coexist:
  ///
  ///   * `bt-failure:<BtFailure.name>` — written by [AppState] itself when it
  ///     knows the category directly (permission denied, no peer chosen, …).
  ///   * `peer-unreachable:<Type>` — written by the BT service / connectivity
  ///     layer when classic BT can't distinguish the failure mode beyond
  ///     "the PC didn't answer." Mapped to [BtFailure.peerUnreachable].
  ///
  /// Legacy raw English strings from pre-T7 builds (e.g. "BT connect failed:
  /// PlatformException(…)") pass through [classifyBtError] for a one-shot
  /// migration — the next BT tick overwrites them with a proper token.
  String? _classifyStoredBtError(String? stored) {
    if (stored == null || stored.isEmpty) return null;
    if (stored.startsWith('bt-failure:')) {
      final name = stored.substring('bt-failure:'.length);
      for (final f in BtFailure.values) {
        if (f.name == name) return btMessageFor(f, _locale);
      }
      return btMessageFor(BtFailure.unknown, _locale);
    }
    if (stored.startsWith('peer-unreachable:')) {
      return btMessageFor(BtFailure.peerUnreachable, _locale);
    }
    return btMessageFor(classifyBtError(stored), _locale);
  }

  /// Token written to storage for a given category. Reading back via
  /// [_classifyStoredBtError] in the user's current locale produces the
  /// rendered text.
  String _btFailureToken(BtFailure kind) => 'bt-failure:${kind.name}';

  /// True when the BT auto-loop should be running: BT enabled, peer bonded,
  /// app currently in the foreground/visible-process lifecycle. The loop
  /// pauses on `paused`/`detached` so a backgrounded process doesn't drain
  /// battery or fight Android's BT stack while the user isn't looking.
  bool _btAutoLoopRunning = false;
  AppLifecycleState _lifecycle = AppLifecycleState.resumed;

  void _refreshBtAutoLoop() {
    final shouldRun = _btEnabled &&
        _btBondedMac != null &&
        _btBondedMac!.isNotEmpty &&
        _lifecycle == AppLifecycleState.resumed;
    if (shouldRun && !_btAutoLoopRunning) {
      _connectivity.startBluetoothAutoLoop();
      _btAutoLoopRunning = true;
    } else if (!shouldRun && _btAutoLoopRunning) {
      _connectivity.stopBluetoothAutoLoop();
      _btAutoLoopRunning = false;
    }
  }

  Future<void> setBtEnabled(bool enabled) async {
    if (enabled) {
      // Android 12+ runtime perms — without these, every BT call fails
      // silently. Must be called from a foreground activity, which is
      // where this toggle lives.
      final granted = await BluetoothPermissions.ensureGranted();
      if (!granted) {
        _btEnabled = false;
        _btLastError = btMessageFor(BtFailure.permissionDenied, _locale);
        await _storage.setBtEnabled(false);
        await _storage.setBtLastError(_btFailureToken(BtFailure.permissionDenied));
        _refreshBtAutoLoop();
        notifyListeners();
        return;
      }
      _btLastError = null;
      await _storage.clearBtLastError();
    }
    _btEnabled = enabled;
    await _storage.setBtEnabled(enabled);
    _refreshBtAutoLoop();
    notifyListeners();
  }

  Future<void> bindBtPeer({required String mac, required String label}) async {
    await _storage.setBtBondedPeer(mac: mac, label: label);
    _btBondedMac = mac;
    _btBondedLabel = label;
    _refreshBtAutoLoop();
    notifyListeners();
  }

  Future<void> unbindBtPeer() async {
    await _storage.clearBtBondedPeer();
    _btBondedMac = null;
    _btBondedLabel = null;
    _refreshBtAutoLoop();
    notifyListeners();
  }

  /// Force one Bluetooth sync cycle right now, bypassing the LAN/cloud
  /// reachability gate. Used by the explicit "Sync now via Bluetooth" button.
  Future<bool> syncViaBluetoothNow() async {
    final mac = _btBondedMac;
    if (mac == null || mac.isEmpty) {
      _btLastError = btMessageFor(BtFailure.noPeerSelected, _locale);
      await _storage.setBtLastError(_btFailureToken(BtFailure.noPeerSelected));
      notifyListeners();
      return false;
    }
    final granted = await BluetoothPermissions.ensureGranted();
    if (!granted) {
      _btLastError = btMessageFor(BtFailure.permissionDenied, _locale);
      await _storage.setBtLastError(_btFailureToken(BtFailure.permissionDenied));
      notifyListeners();
      return false;
    }
    final ok = await _connectivity.syncViaBluetooth(mac);
    await _loadBtState();
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
    await _loadBtState();
    _refreshBtAutoLoop();
  }

  void setLocale(String locale) {
    _locale = locale;
    // Re-render any visible BT error banner in the new locale. Reads the
    // stored token through _classifyStoredBtError, so a previously-displayed
    // "Turn on Bluetooth to sync." flips to "قم بتشغيل البلوتوث للمزامنة."
    // immediately instead of waiting for the next BT cycle.
    unawaited(_loadBtState());
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
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _lifecycle = state;
    if (state == AppLifecycleState.resumed) {
      // Background or foreground BT ticks may have updated bt_last_sync_at /
      // bt_last_error in storage. Pull fresh values into UI state.
      unawaited(_loadBtState());
    }
    _refreshBtAutoLoop();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _connectivity.stopBluetoothAutoLoop();
    _connectivity.dispose();
    super.dispose();
  }
}
