import 'dart:async';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'bluetooth_permissions.dart';
import 'clinic_api.dart';
import 'cloud_sync_service.dart';
import 'internet_sync_service.dart';
import 'bluetooth_sync_service.dart';
import 'local_storage_service.dart';
import '../utils/sync_banner.dart';

enum SyncStatus { idle, syncing, synced, offline, error }

/// Orchestrates sync against the best available link in this order:
///   1. LAN / local server  (`X-Device-Token` auth, if a local URL is configured)
///   2. Cloud node          (`X-Clinic-Token` auth, if a cloud account is paired)
///   3. Bluetooth fallback  (peer-to-peer, when offline)
///
/// Before each internet sync we re-point [ClinicApi] at whichever target is
/// reachable, so the same [InternetSyncService] code works for both.
class ConnectivitySyncService {
  ConnectivitySyncService({
    required InternetSyncService internet,
    required BluetoothSyncService bluetooth,
    required LocalStorageService storage,
    required ClinicApi api,
    CloudSyncService? cloud,
  })  : _internet = internet,
        _bluetooth = bluetooth,
        _storage = storage,
        _api = api,
        _cloud = cloud ?? CloudSyncService() {
    _connectivitySub =
        Connectivity().onConnectivityChanged.listen(_onConnectivityChanged);
  }

  final InternetSyncService _internet;
  final BluetoothSyncService _bluetooth;
  final LocalStorageService _storage;
  final ClinicApi _api;
  final CloudSyncService _cloud;

  SyncStatus _status = SyncStatus.idle;
  String? _statusMessage;
  SyncLink _activeLink = SyncLink.none;
  bool _hasSyncedOnce = false;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;

  final _statusController = StreamController<SyncStatus>.broadcast();

  Stream<SyncStatus> get statusStream => _statusController.stream;
  SyncStatus get status => _status;
  String? get statusMessage => _statusMessage;
  SyncLink get activeLink => _activeLink;
  bool get hasSyncedOnce => _hasSyncedOnce;

  void _emit(SyncStatus s, [String? msg]) {
    // Drop identical consecutive emissions so a routine re-sync that changes
    // nothing doesn't re-flash the banner (the "synced/not-synced keeps
    // popping up" complaint).
    if (!shouldEmitSyncStatus(_status, _statusMessage, s, msg)) return;
    _status = s;
    _statusMessage = msg;
    _statusController.add(s);
  }

  Future<void> _onConnectivityChanged(List<ConnectivityResult> results) async {
    final hasNet = results.any((r) =>
        r == ConnectivityResult.wifi || r == ConnectivityResult.mobile);
    if (hasNet) {
      await syncNow();
    } else {
      _activeLink = SyncLink.none;
      _emit(SyncStatus.offline, 'Offline — use Bluetooth to sync');
    }
  }

  Future<void> syncNow() async {
    if (_status == SyncStatus.syncing) return;
    _emit(SyncStatus.syncing, 'Syncing…');
    try {
      final link = await _configureBestTarget();
      if (link == null) {
        _activeLink = SyncLink.none;
        _emit(SyncStatus.offline,
            'No clinic server is reachable — use Bluetooth to sync');
        return;
      }
      _activeLink = link;
      await _internet.syncAll();
      _hasSyncedOnce = true;
      _emit(SyncStatus.synced, 'Synced · ${_linkLabel(link)}');
    } catch (_) {
      _emit(SyncStatus.error, 'Sync failed');
    }
  }

  /// Picks the best internet target and points [ClinicApi] at it.
  /// Returns the link that was configured, or `null` if nothing is reachable.
  Future<SyncLink?> _configureBestTarget() async {
    // 1) LAN / local server — paired devices use a device token here.
    final localUrl = await _storage.getLocalUrl();
    final deviceToken = await _storage.getDeviceToken();
    if (localUrl != null &&
        localUrl.isNotEmpty &&
        deviceToken != null &&
        deviceToken.isNotEmpty &&
        await _cloud.isReachable(localUrl)) {
      _api.configure(
        baseUrl: localUrl,
        deviceToken: deviceToken,
        clinicToken: null,
        link: SyncLink.localWifi,
      );
      return SyncLink.localWifi;
    }
    // 2) Cloud node — the clinic token both authenticates and selects the tenant.
    final cloudUrl = await _storage.getCloudUrl();
    final clinicToken = await _storage.getCloudClinicToken();
    if (cloudUrl != null &&
        cloudUrl.isNotEmpty &&
        clinicToken != null &&
        clinicToken.isNotEmpty &&
        await _cloud.isReachable(cloudUrl, clinicToken: clinicToken)) {
      _api.configure(
        baseUrl: cloudUrl,
        deviceToken: null,
        clinicToken: clinicToken,
        link: SyncLink.cloud,
      );
      return SyncLink.cloud;
    }
    return null;
  }

  String _linkLabel(SyncLink link) {
    switch (link) {
      case SyncLink.localWifi:
        return 'Local Wi-Fi';
      case SyncLink.cloud:
        return 'Cloud';
      case SyncLink.bluetooth:
        return 'Bluetooth';
      case SyncLink.none:
        return '—';
    }
  }

  Future<bool> syncViaBluetooth(String bondedMac) async {
    _emit(SyncStatus.syncing, 'Bluetooth sync…');
    final result = await _bluetooth.runOneSyncCycle(bondedMac);
    if (result.success) {
      _activeLink = SyncLink.bluetooth;
      _emit(SyncStatus.synced, 'Synced · Bluetooth');
      await _storage.setBtLastSyncAt(DateTime.now().toIso8601String());
      await _storage.clearBtLastError();
      return true;
    }
    _activeLink = SyncLink.none;
    await _storage.setBtLastError(result.errorMessage ?? 'unknown');
    _emit(SyncStatus.error, result.errorMessage ?? 'Bluetooth sync failed');
    return false;
  }

  Timer? _btAutoTimer;

  /// Start the auto-fallback BT loop. Idempotent; safe to call repeatedly.
  void startBluetoothAutoLoop({Duration interval = const Duration(seconds: 30)}) {
    _btAutoTimer?.cancel();
    _btAutoTimer = Timer.periodic(interval, (_) => _btAutoTick());
    // also tick immediately so we don't wait 30 s on first activation
    unawaited(_btAutoTick());
  }

  void stopBluetoothAutoLoop() {
    _btAutoTimer?.cancel();
    _btAutoTimer = null;
  }

  Future<void> _btAutoTick({bool force = false}) async {
    if (_status == SyncStatus.syncing) return;
    final mac = await _storage.getBtBondedMac();
    if (mac == null || mac.isEmpty) return;
    final enabled = await _storage.getBtEnabled();
    if (!enabled) return;
    // Non-prompting status check — if the user revoked BT permissions after
    // enabling the toggle, the next session would just hang. Bail early
    // with a clear error.
    if (!await BluetoothPermissions.areGranted()) {
      // Token (not English) — AppState renders it in the user's locale on read.
      await _storage.setBtLastError('bt-failure:permissionDenied');
      return;
    }
    if (!force) {
      // Skip if LAN or cloud just synced — fallback-only mode for the auto-loop.
      final lanOk = await _isLanReachable();
      if (lanOk) return;
      final cloudOk = await _isCloudReachable();
      if (cloudOk) return;
    }
    await syncViaBluetooth(mac);
  }

  Future<bool> _isLanReachable() async {
    final url = await _storage.getLocalUrl();
    final token = await _storage.getDeviceToken();
    if (url == null || url.isEmpty || token == null || token.isEmpty) return false;
    return _cloud.isReachable(url);
  }

  Future<bool> _isCloudReachable() async {
    final url = await _storage.getCloudUrl();
    final token = await _storage.getCloudClinicToken();
    if (url == null || url.isEmpty || token == null || token.isEmpty) return false;
    return _cloud.isReachable(url, clinicToken: token);
  }

  Future<String?> getLastSyncTime() => _internet.getLastSyncTime();

  void dispose() {
    _btAutoTimer?.cancel();
    _connectivitySub?.cancel();
    _statusController.close();
  }
}
