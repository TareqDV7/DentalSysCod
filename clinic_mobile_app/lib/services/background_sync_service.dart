import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter_background_service/flutter_background_service.dart';

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
/// Filled in by Task 3 — leave as stub for now.
@pragma('vm:entry-point')
void bgSyncOnStart(ServiceInstance service) {
  // STUB: Task 3 wires the sync isolate (ConnectivitySyncService, BT loop,
  // force_sync + stopService handlers). Do not implement here.
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
      await _client.configure();
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
