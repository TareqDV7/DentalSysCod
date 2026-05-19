import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart' show WidgetsFlutterBinding;
import 'package:flutter_background_service/flutter_background_service.dart';
import 'database_service.dart';
import 'local_storage_service.dart';
import 'clinic_api.dart';
import 'cloud_sync_service.dart';
import 'internet_sync_service.dart';
import 'bluetooth_sync_service.dart';
import 'connectivity_sync_service.dart';
import 'device_service.dart';

/// Thin interface over the parts of [FlutterBackgroundService] we use.
/// Lets unit tests inject a fake without touching platform channels.
abstract class BgServiceClient {
  Future<bool> isRunning();
  Future<bool> configure();
  Future<bool> startService();
  void invoke(String event, [Map<String, dynamic>? data]);
  Stream<Map<String, dynamic>?> on(String event);
}

class _ProductionBgServiceClient implements BgServiceClient {
  final _svc = FlutterBackgroundService();

  @override
  Future<bool> isRunning() => _svc.isRunning();

  @override
  Future<bool> configure() async {
    return _svc.configure(
      androidConfiguration: AndroidConfiguration(
        onStart: bgSyncOnStart,
        autoStart: false,
        isForegroundMode: true,
        notificationChannelId: 'clinic_sync',
        initialNotificationTitle: 'Clinic sync active',
        initialNotificationContent: 'Listening for the clinic PC',
        foregroundServiceNotificationId: 9101,
      ),
      iosConfiguration: IosConfiguration(autoStart: false),
    );
  }

  @override
  Future<bool> startService() => _svc.startService();

  @override
  void invoke(String event, [Map<String, dynamic>? data]) =>
      _svc.invoke(event, data);

  @override
  Stream<Map<String, dynamic>?> on(String event) => _svc.on(event);
}

/// Top-level function that runs inside the background isolate.
/// Background isolate: no UI, no Provider. Build a fresh dependency
/// graph that mirrors what AppState builds in the UI isolate. Each
/// isolate opens its own sqflite connection to the same file; WAL
/// handles writer-writer concurrency.
@pragma('vm:entry-point')
void bgSyncOnStart(ServiceInstance service) async {
  WidgetsFlutterBinding.ensureInitialized();
  // The library entrypoint already calls ensureInitialized; this is
  // defensive in case the library implementation changes.

  late final LocalStorageService storage;
  late final ConnectivitySyncService connectivity;
  StreamSubscription? forceSyncSub;
  StreamSubscription? stopSub;

  try {
    storage = LocalStorageService();
    final db = DatabaseService.instance;
    final api = ClinicApi();
    final baseUrl = await storage.getBaseUrl();
    if (baseUrl != null) api.baseUrl = baseUrl;
    final token = await storage.getDeviceToken();
    if (token != null) api.deviceToken = token;
    final clinicToken = await storage.getCloudClinicToken();
    if (clinicToken != null) api.clinicToken = clinicToken;

    final cloud = CloudSyncService();
    final internet = InternetSyncService(db, api);
    final deviceService = DeviceService();
    final bluetooth = BluetoothSyncService.production(
      deviceTokenLoader: storage.getDeviceToken,
      deviceTokenSaver: storage.setDeviceToken,
      deviceIdLoader: deviceService.getDeviceId,
      sinceLoader: () => db.getSyncMeta('last_sync_cursor'),
      onExport: (exported) async {
        await internet.applyExportedDelta(exported);
      },
      buildPushPayload: internet.buildPushPayload,
      onPushAcked: (payload) async {
        await internet.markPayloadAsSynced(payload);
      },
      clientVersion: '1.0.0',
    );
    connectivity = ConnectivitySyncService(
      internet: internet,
      bluetooth: bluetooth,
      storage: storage,
      api: api,
      cloud: cloud,
    );

    // Start the 30s BT auto-fallback loop here, in the sync isolate.
    // This is the whole point of the refactor: the Timer now lives in
    // a background-service-anchored isolate, so it keeps ticking when
    // the app is backgrounded.
    connectivity.startBluetoothAutoLoop();
  } catch (e) {
    // Setup failed (keystore unlock failure, plugin channel not ready,
    // DB open error). Record the diagnostic so the UI can surface it on
    // next resume, then exit the isolate cleanly.
    try {
      await LocalStorageService().setBtLastError(
          'Background sync failed to start: ${e.toString()}');
    } catch (_) {
      // Storage itself failed — nothing we can do from here.
    }
    service.stopSelf();
    return;
  }

  // Listen for manual "Sync now" from the UI isolate. Subscription is
  // stored so the stopService handler can cancel it.
  forceSyncSub = service.on('force_sync').listen((_) async {
    try {
      await connectivity.forceTick();
      service.invoke('sync_finished', {
        'ok': true,
        'lastSyncAt': await storage.getBtLastSyncAt(),
      });
    } catch (e) {
      service.invoke('sync_finished', {
        'ok': false,
        'error': e.toString(),
      });
    }
  });

  // Listen for shutdown from the UI isolate. Cancels both subscriptions
  // before tearing down the sync graph.
  stopSub = service.on('stopService').listen((_) async {
    await forceSyncSub?.cancel();
    await stopSub?.cancel();
    connectivity.stopBluetoothAutoLoop();
    connectivity.dispose();
    service.stopSelf();
  });
}

class BackgroundSyncService {
  final BgServiceClient _client;
  bool _configured = false;

  BackgroundSyncService.production() : _client = _ProductionBgServiceClient();

  @visibleForTesting
  BackgroundSyncService.forTest({required BgServiceClient client})
      : _client = client;

  Future<void> start() async {
    if (await _client.isRunning()) return;
    if (!_configured) {
      final ok = await _client.configure();
      if (!ok) {
        throw StateError(
            'BackgroundSyncService: FlutterBackgroundService.configure() returned false. '
            'Check AndroidManifest <service> declaration and notification channel.');
      }
      _configured = true;
    }
    await _client.startService();
  }

  Future<void> stop() async {
    if (!await _client.isRunning()) return;
    _client.invoke('stopService');
  }

  void forceSync() => _client.invoke('force_sync');

  Stream<Map<String, dynamic>?> get onSyncFinished =>
      _client.on('sync_finished');
}
