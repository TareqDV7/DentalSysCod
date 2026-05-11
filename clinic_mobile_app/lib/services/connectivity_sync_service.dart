import 'dart:async';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'internet_sync_service.dart';
import 'bluetooth_sync_service.dart';

enum SyncStatus { idle, syncing, synced, offline, error }

class ConnectivitySyncService {
  final InternetSyncService _internet;
  final BluetoothSyncService _bluetooth;

  SyncStatus _status = SyncStatus.idle;
  String? _statusMessage;
  bool _hasSyncedOnce = false;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;

  final _statusController = StreamController<SyncStatus>.broadcast();

  ConnectivitySyncService(this._internet, this._bluetooth) {
    _connectivitySub = Connectivity()
        .onConnectivityChanged
        .listen(_onConnectivityChanged);
  }

  Stream<SyncStatus> get statusStream => _statusController.stream;
  SyncStatus get status => _status;
  String? get statusMessage => _statusMessage;

  void _emit(SyncStatus s, [String? msg]) {
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
      _emit(SyncStatus.offline, 'Offline — use Bluetooth to sync');
    }
  }

  Future<void> syncNow() async {
    if (_status == SyncStatus.syncing) return;
    _emit(SyncStatus.syncing, 'Syncing…');
    try {
      await _internet.syncAll();
      _hasSyncedOnce = true;
      _emit(SyncStatus.synced, 'Synced');
    } catch (e) {
      _emit(SyncStatus.error, 'Sync failed');
    }
  }

  Future<bool> syncViaBluetooth() async {
    _emit(SyncStatus.syncing, 'Bluetooth sync…');
    final ok = await _bluetooth.scanAndSync();
    if (ok) {
      _emit(SyncStatus.synced, 'Synced via Bluetooth');
    } else {
      _emit(SyncStatus.error,
          _bluetooth.lastError ?? 'Bluetooth sync failed');
    }
    return ok;
  }

  Future<String?> getLastSyncTime() => _internet.getLastSyncTime();

  bool get hasSyncedOnce => _hasSyncedOnce;

  void dispose() {
    _connectivitySub?.cancel();
    _statusController.close();
    _bluetooth.dispose();
  }
}
