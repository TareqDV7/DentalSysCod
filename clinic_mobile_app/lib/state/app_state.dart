import 'dart:async';

import 'package:flutter/material.dart';
import '../services/clinic_api.dart';
import '../services/api_client.dart';
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
import '../utils/activation_token.dart';
import '../utils/bt_error_message.dart';
import '../utils/clinic_link.dart';
import '../utils/clinic_profile.dart';
import '../utils/prefs_codec.dart';
import '../config/app_config.dart';

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
  String _doctorNameEn = AppBranding.doctorName;
  String _doctorNameAr = AppBranding.doctorNameAr;
  String? _serialNumber;
  String? _licenseExpiresAt;

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
  String get doctorNameEn => _doctorNameEn;
  String get doctorNameAr => _doctorNameAr;

  /// The doctor name to show for the current locale (Arabic in Arabic, English
  /// otherwise), falling back across languages when one is blank.
  String get doctorName =>
      resolveDoctorName(_doctorNameEn, _doctorNameAr, _locale);

  /// The activated clinic serial (raw); null until the device is activated.
  String? get serialNumber => _serialNumber;

  /// ISO timestamp the license is valid until, decoded from the activation key.
  String? get licenseExpiresAt => _licenseExpiresAt;

  bool get isActivated => (_serialNumber ?? '').isNotEmpty;

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
    final dnEn = await _storage.getDoctorNameEn();
    final dnAr = await _storage.getDoctorNameAr();
    if (dnEn != null && dnEn.isNotEmpty) _doctorNameEn = dnEn;
    if (dnAr != null && dnAr.isNotEmpty) _doctorNameAr = dnAr;
    _serialNumber = await _storage.getSerialNumber();
    _licenseExpiresAt = await _storage.getLicenseExpiry();
    // Restore the saved UI preferences — without this the theme reset to light
    // (and the language to English) on every cold start.
    _themeMode = decodeThemeMode(await _storage.getThemeMode());
    _locale = decodeLocale(await _storage.getLocale());
    _cloudUrl = cloudUrl;
    _hasCloudAccount = (cloudUrl != null && cloudUrl.isNotEmpty) &&
        (clinicToken != null && clinicToken.isNotEmpty);
    notifyListeners();
    // Sync first, then pull the shared clinic profile — sequenced so the one-off
    // clinic-settings call doesn't re-point ClinicApi mid-sync.
    unawaited(() async {
      try {
        await sync.syncNow();
      } catch (error) {
        debugPrint('Initial sync failed: $error');
      }
      await refreshClinicProfile();
    }());
    await _loadBtState();
    _refreshBtAutoLoop();
  }

  /// Persist a new doctor name locally, reflect it immediately, and push it to
  /// the server best-effort. If the push can't reach a server (offline), the
  /// edit is marked pending so the next refresh re-pushes it instead of being
  /// overwritten by a stale server value.
  Future<void> setDoctorNames(String en, String ar) async {
    final e = en.trim();
    final a = ar.trim();
    if (e.isNotEmpty) _doctorNameEn = e;
    if (a.isNotEmpty) _doctorNameAr = a;
    await _storage.setDoctorNameEn(_doctorNameEn);
    await _storage.setDoctorNameAr(_doctorNameAr);
    notifyListeners();
    final pushed = await sync.pushClinicSettings(
        doctorName: _doctorNameEn, doctorNameAr: _doctorNameAr);
    await _storage.setDoctorNamePending(!pushed);
  }

  /// Best-effort reconcile of the shared doctor name with the server. A pending
  /// local edit is re-pushed (never clobbered); otherwise the server value (the
  /// shared source of truth, written by the desktop too) is pulled in.
  Future<void> refreshClinicProfile() async {
    if (await _storage.getDoctorNamePending()) {
      final pushed = await sync.pushClinicSettings(
          doctorName: _doctorNameEn, doctorNameAr: _doctorNameAr);
      if (pushed) await _storage.setDoctorNamePending(false);
      return;
    }
    final data = await sync.fetchClinicSettings();
    if (data == null) return;
    final en = (data['doctor_name'] ?? '').toString().trim();
    final ar = (data['doctor_name_ar'] ?? '').toString().trim();
    var changed = false;
    if (en.isNotEmpty && en != _doctorNameEn) {
      _doctorNameEn = en;
      await _storage.setDoctorNameEn(en);
      changed = true;
    }
    if (ar.isNotEmpty && ar != _doctorNameAr) {
      _doctorNameAr = ar;
      await _storage.setDoctorNameAr(ar);
      changed = true;
    }
    if (changed) notifyListeners();
  }

  void setLocale(String locale) {
    _locale = locale;
    unawaited(_storage.setLocale(locale));
    // Re-render any visible BT error banner in the new locale. Reads the
    // stored token through _classifyStoredBtError, so a previously-displayed
    // "Turn on Bluetooth to sync." flips to "قم بتشغيل البلوتوث للمزامنة."
    // immediately instead of waiting for the next BT cycle.
    unawaited(_loadBtState());
    notifyListeners();
  }

  void setThemeMode(ThemeMode mode) {
    _themeMode = mode;
    unawaited(_storage.setThemeMode(encodeThemeMode(mode)));
    notifyListeners();
  }

  Future<void> updateServerUrl(String url) async {
    api.baseUrl = url;
    await _storage.setBaseUrl(url);
    await _storage.setLocalUrl(url);
    notifyListeners();
  }

  /// Link this device to its clinic using the vendor-signed **activation key**
  /// — the only thing the user types. The serial is read from the key, the
  /// device registers against the baked cloud node (signature verified there),
  /// and the returned clinic token is persisted so cloud sync runs automatically.
  ///
  /// Does NOT touch the device token (that belongs to the LAN/Bluetooth pairing
  /// flow); cloud sync authenticates with the clinic token instead.
  ///
  /// Throws [ApiException] if the key is malformed or the cloud rejects it.
  Future<CloudAccountInfo> activateWithKey(
    String activationKey, {
    String? clinicName,
  }) async {
    final key = activationKey.trim();
    final parsed = ActivationToken.tryParse(key);
    if (parsed == null) {
      throw const ApiException('That activation key is not valid.');
    }
    final name = (clinicName != null && clinicName.trim().isNotEmpty)
        ? clinicName.trim()
        : (parsed.clinicName ?? 'Clinic');
    const cloudUrl = CloudSyncService.defaultCloudUrl;
    // Capture the clinic this device was linked to BEFORE we overwrite it, so we
    // can tell whether this key moves the device to a different clinic.
    final previousClinicId = await _storage.getCloudClinicId();
    final info = await cloud.register(
      cloudUrl: cloudUrl,
      serialNumber: parsed.serial,
      clinicName: name,
      offlineToken: key,
    );
    await _storage.setSerialNumber(parsed.serial);
    await _storage.setClinicName(name);
    if (parsed.expiresAt != null && parsed.expiresAt!.isNotEmpty) {
      await _storage.setLicenseExpiry(parsed.expiresAt!);
    }
    await _storage.setCloudAccount(
      cloudUrl: cloudUrl,
      clinicToken: info.clinicToken,
      clinicId: info.clinicId,
    );
    if (clinicSwitchRequiresLocalReset(
        previousClinicId: previousClinicId, newClinicId: info.clinicId)) {
      // Joining a DIFFERENT clinic: discard this device's old-clinic records so
      // they neither linger nor collide by row-id, then let the full pull below
      // mirror the new clinic. Without this, a stale sync cursor + already-synced
      // flags make both legs transfer nothing while the banner reads "Synced".
      await db.wipeLocalClinicData();
    }
    _clinicName = name;
    _cloudUrl = cloudUrl;
    _hasCloudAccount = true;
    _serialNumber = parsed.serial;
    if (parsed.expiresAt != null && parsed.expiresAt!.isNotEmpty) {
      _licenseExpiresAt = parsed.expiresAt;
    }
    api.clinicToken = info.clinicToken;
    notifyListeners();
    // First sync right away against the freshly-linked cloud target.
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
