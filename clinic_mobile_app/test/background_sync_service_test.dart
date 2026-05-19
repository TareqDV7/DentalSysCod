import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/background_sync_service.dart';

class _FailingConfigureFake implements BgServiceClient {
  @override
  Future<bool> isRunning() async => false;
  @override
  Future<bool> configure() async => false;
  @override
  Future<bool> startService() async => true;
  @override
  void invoke(String event, [Map<String, dynamic>? data]) {}
  @override
  Stream<Map<String, dynamic>?> on(String event) => const Stream.empty();
}

class _FakeBgServiceClient implements BgServiceClient {
  bool running = false;
  int startServiceCalls = 0;
  int configureCalls = 0;
  final List<String> invokes = [];

  @override
  Future<bool> isRunning() async => running;

  @override
  Future<bool> configure() async {
    configureCalls++;
    return true;
  }

  @override
  Future<bool> startService() async {
    startServiceCalls++;
    running = true;
    return true;
  }

  @override
  void invoke(String event, [Map<String, dynamic>? data]) {
    invokes.add(event);
  }

  @override
  Stream<Map<String, dynamic>?> on(String event) => const Stream.empty();
}

void main() {
  test('start() is idempotent — second call does nothing if already running',
      () async {
    final fake = _FakeBgServiceClient();
    final svc = BackgroundSyncService.forTest(client: fake);
    await svc.start();
    await svc.start();
    expect(fake.startServiceCalls, 1);
    expect(fake.configureCalls, 1);
  });

  test('stop() invokes stopService when running', () async {
    final fake = _FakeBgServiceClient()..running = true;
    final svc = BackgroundSyncService.forTest(client: fake);
    await svc.stop();
    expect(fake.invokes, ['stopService']);
  });

  test('stop() is a no-op when not running', () async {
    final fake = _FakeBgServiceClient(); // running = false
    final svc = BackgroundSyncService.forTest(client: fake);
    await svc.stop();
    expect(fake.invokes, isEmpty);
  });

  test('forceSync() emits the force_sync event', () {
    final fake = _FakeBgServiceClient();
    final svc = BackgroundSyncService.forTest(client: fake);
    svc.forceSync();
    expect(fake.invokes, ['force_sync']);
  });

  test('start() throws StateError when configure() returns false', () async {
    final fake = _FailingConfigureFake();
    final svc = BackgroundSyncService.forTest(client: fake);
    expect(svc.start(), throwsA(isA<StateError>()));
  });
}
