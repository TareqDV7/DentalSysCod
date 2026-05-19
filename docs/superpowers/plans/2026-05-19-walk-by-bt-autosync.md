# Walk-by Bluetooth Autosync — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the BT auto-fallback Timer from the UI isolate into a foreground-service-owned background isolate so walk-by sync fires while the app is backgrounded.

**Architecture:** Add a thin `BackgroundSyncService` wrapper around `flutter_background_service`. The service's `onStart` (which runs in a separate Dart isolate) constructs its own `ConnectivitySyncService` instance and calls `startBluetoothAutoLoop()` there. `AppState` and the Settings screen route through `BackgroundSyncService` instead of touching the Timer directly. Manual "Sync now" sends a `force_sync` event to the sync isolate, eliminating the two-isolate BT-SPP race.

**Tech Stack:** Flutter / Dart, `flutter_background_service: ^5.0.5` (already in pubspec), `sqflite`, `flutter_bluetooth_serial`. AndroidManifest already declares the foreground service + `FOREGROUND_SERVICE_DATA_SYNC` permission (lines 15–17, 64–68).

**Reference spec:** `docs/superpowers/specs/2026-05-19-walk-by-bt-autosync-design.md`

---

## File Structure

**New (2 files):**
- `clinic_mobile_app/lib/services/background_sync_service.dart` — wrapper class + `BgServiceClient` interface + `_ProductionClient` impl + top-level `bgSyncOnStart` for the sync isolate. ~140 LOC.
- `clinic_mobile_app/test/background_sync_service_test.dart` — unit tests against a `_FakeBgServiceClient`. ~80 LOC, 5 cases.

**Modified (4 files):**
- `clinic_mobile_app/lib/services/connectivity_sync_service.dart` — small surgical change: add `force: false` parameter to `_btAutoTick` so manual override can bypass the LAN/cloud reachability gate.
- `clinic_mobile_app/lib/state/app_state.dart` — instantiate `BackgroundSyncService`; replace `_connectivity.startBluetoothAutoLoop()` calls in `init`, `setBtEnabled`, `bindBtPeer` with `_bgSync.start()`; replace `stopBluetoothAutoLoop()` with `_bgSync.stop()`; route `syncViaBluetoothNow` through `_bgSync.forceSync()`. Add `WidgetsBindingObserver` hook to refresh `_loadBtState()` on app resume.
- `clinic_mobile_app/lib/main.dart` — call `_appState.startBackgroundSync()` after `AppState.init()` completes.
- `clinic_mobile_app/lib/screens/settings_screen.dart` — collapse the BT Sync card to three states (Off / Active · last sync N min ago / Syncing…); demote `Sync now` to an inner Advanced row inside an `ExpansionTile`.

**Already in place — do not re-touch:**
- `clinic_mobile_app/android/app/src/main/AndroidManifest.xml` — `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_DATA_SYNC`, `POST_NOTIFICATIONS` permissions and the `<service ... foregroundServiceType="dataSync" />` declaration are already there from when `flutter_background_service` was added.
- `clinic_mobile_app/pubspec.yaml` — `flutter_background_service: ^5.0.5` already declared.

---

## Task 1: Add `force` flag to `_btAutoTick` to bypass LAN/cloud gate

Smallest pre-requisite: manual "Sync now" needs to run a BT cycle even when LAN/cloud are reachable. Today `syncViaBluetoothNow` calls `syncViaBluetooth(mac)` directly. After the refactor, the sync isolate owns BT — so we need `_btAutoTick(force: true)` to skip the gate.

`ConnectivitySyncService` has heavy dependencies (`InternetSyncService`, `BluetoothSyncService`, `LocalStorageService`, `ClinicApi`, `CloudSyncService`); a real unit test for the gate-bypass would require mocking all five and there's no precedent for that in the codebase. Skip the unit test on this 1-line API addition — hardware smoke in Task 8 covers the force path end-to-end.

**Files:**
- Modify: `clinic_mobile_app/lib/services/connectivity_sync_service.dart:174-193`

- [ ] **Step 1: Read the current `_btAutoTick`**

Open `clinic_mobile_app/lib/services/connectivity_sync_service.dart`, locate `_btAutoTick` at line 174. Current body:

```dart
Future<void> _btAutoTick() async {
  if (_status == SyncStatus.syncing) return;
  final mac = await _storage.getBtBondedMac();
  if (mac == null || mac.isEmpty) return;
  final enabled = await _storage.getBtEnabled();
  if (!enabled) return;
  if (!await BluetoothPermissions.areGranted()) {
    await _storage.setBtLastError('Bluetooth permission revoked');
    return;
  }
  final lanOk = await _isLanReachable();
  if (lanOk) return;
  final cloudOk = await _isCloudReachable();
  if (cloudOk) return;
  await syncViaBluetooth(mac);
}
```

- [ ] **Step 2: Modify the method to accept a `force` flag**

Replace lines 174–193 with:

```dart
Future<void> _btAutoTick({bool force = false}) async {
  if (_status == SyncStatus.syncing) return;
  final mac = await _storage.getBtBondedMac();
  if (mac == null || mac.isEmpty) return;
  final enabled = await _storage.getBtEnabled();
  if (!enabled) return;
  if (!await BluetoothPermissions.areGranted()) {
    await _storage.setBtLastError('Bluetooth permission revoked');
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
```

Update the Timer callback on line 164 to keep the default (no `force`):

```dart
_btAutoTimer = Timer.periodic(interval, (_) => _btAutoTick());
```

(The default `force: false` keeps existing behavior. No change needed at the call site.)

- [ ] **Step 3: Add a public `forceTick()` entry point**

Append below the existing `_btAutoTick`:

```dart
/// Public entry point that runs one BT sync attempt right now, bypassing
/// the LAN/cloud reachability gate. Used by `BackgroundSyncService.forceSync`
/// when the user taps "Sync now via Bluetooth".
Future<void> forceTick() => _btAutoTick(force: true);
```

- [ ] **Step 4: Run analyzer + tests**

```
cd clinic_mobile_app
flutter analyze
flutter test
```

Expected: analyzer clean, all existing tests pass (27/27).

- [ ] **Step 5: Commit**

```
rtk git add clinic_mobile_app/lib/services/connectivity_sync_service.dart
rtk git commit -m "feat(mobile-bt): add forceTick() that bypasses LAN/cloud gate"
```

---

## Task 2: Create `BackgroundSyncService` wrapper with idempotent `start()`

The wrapper holds the `flutter_background_service` configuration and exposes start/stop/forceSync. Tests use a `_FakeBgServiceClient` injected via the constructor — same pattern as `BluetoothSyncService.forTest` (see `clinic_mobile_app/test/bluetooth_sync_service_test.dart`).

**Files:**
- Create: `clinic_mobile_app/lib/services/background_sync_service.dart`
- Create: `clinic_mobile_app/test/background_sync_service_test.dart`

- [ ] **Step 1: Write failing test for idempotent start**

Create `clinic_mobile_app/test/background_sync_service_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/background_sync_service.dart';

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
}
```

- [ ] **Step 2: Run the test, confirm it fails**

```
cd clinic_mobile_app
flutter test test/background_sync_service_test.dart
```

Expected: FAIL with `Error: Couldn't resolve the package 'clinic_mobile_app/services/background_sync_service.dart'`.

- [ ] **Step 3: Write minimal implementation**

Create `clinic_mobile_app/lib/services/background_sync_service.dart`:

```dart
import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_background_service_android/flutter_background_service_android.dart';

/// Thin interface over the parts of `FlutterBackgroundService` we use.
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
/// Will be filled in by Task 3.
@pragma('vm:entry-point')
void bgSyncOnStart(ServiceInstance service) {
  // Stub for Task 2. Real wiring lands in Task 3.
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

  Stream<Map<String, dynamic>?> get onSyncFinished => _client.on('sync_finished');
}
```

- [ ] **Step 4: Run the test, confirm it passes**

```
flutter test test/background_sync_service_test.dart
```

Expected: PASS (1 test).

- [ ] **Step 5: Add three more tests for `stop()`, `forceSync()`, idempotent-stop**

Append to `background_sync_service_test.dart` `main()`:

```dart
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
```

- [ ] **Step 6: Run all tests + analyzer**

```
flutter analyze
flutter test
```

Expected: analyzer clean. 30 tests pass (27 existing + 3 new in this file… wait, 4 new). Total: 31.

- [ ] **Step 7: Commit**

```
rtk git add clinic_mobile_app/lib/services/background_sync_service.dart clinic_mobile_app/test/background_sync_service_test.dart
rtk git commit -m "feat(mobile-bt): BackgroundSyncService wrapper around flutter_background_service"
```

---

## Task 3: Wire the sync-isolate `onStart` handler

The `bgSyncOnStart` stub from Task 2 becomes real here. It runs in a separate Dart isolate when the foreground service starts — that isolate has no UI / Provider, so it constructs everything it needs from scratch: `LocalStorageService`, `DatabaseService.instance`, `ClinicApi`, `BluetoothSyncService.production`, `ConnectivitySyncService`. Then it calls `startBluetoothAutoLoop()` (the *same* call `AppState` used to make in the UI isolate) and listens for `force_sync` / `stopService` events from the UI.

Cannot be unit-tested in pure Dart (uses platform-channel-only `FlutterBackgroundService.invoke` / `.on`); covered by the hardware smoke in Task 8.

**Files:**
- Modify: `clinic_mobile_app/lib/services/background_sync_service.dart`

- [ ] **Step 1: Replace the `bgSyncOnStart` stub with the real handler**

Find this in `background_sync_service.dart`:

```dart
@pragma('vm:entry-point')
void bgSyncOnStart(ServiceInstance service) {
  // Stub for Task 2. Real wiring lands in Task 3.
}
```

Replace with:

```dart
@pragma('vm:entry-point')
void bgSyncOnStart(ServiceInstance service) async {
  // Background isolate: no UI, no Provider. Build a fresh dependency
  // graph that mirrors what AppState builds in the UI isolate. Each
  // isolate opens its own sqflite connection to the same file; WAL
  // handles the writer-writer concurrency.
  WidgetsFlutterBinding.ensureInitialized();
  final storage = LocalStorageService();
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
  final connectivity = ConnectivitySyncService(
    internet: internet,
    bluetooth: bluetooth,
    storage: storage,
    api: api,
    cloud: cloud,
  );

  // Start the 30s BT auto-fallback loop here, in the sync isolate. This
  // is the whole point of the refactor: the Timer now lives in a
  // background-service-anchored isolate, so it keeps ticking when the
  // app is backgrounded.
  connectivity.startBluetoothAutoLoop();

  // Listen for manual "Sync now" from the UI isolate.
  service.on('force_sync').listen((_) async {
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

  // Listen for shutdown from the UI isolate.
  service.on('stopService').listen((_) {
    connectivity.stopBluetoothAutoLoop();
    connectivity.dispose();
    service.stopSelf();
  });
}
```

- [ ] **Step 2: Add the missing imports at the top of `background_sync_service.dart`**

```dart
import 'package:flutter/widgets.dart' show WidgetsFlutterBinding;
import 'database_service.dart';
import 'local_storage_service.dart';
import 'clinic_api.dart';
import 'cloud_sync_service.dart';
import 'internet_sync_service.dart';
import 'bluetooth_sync_service.dart';
import 'connectivity_sync_service.dart';
import 'device_service.dart';
```

- [ ] **Step 3: Run analyzer**

```
cd clinic_mobile_app
flutter analyze
```

Expected: clean. If `WidgetsFlutterBinding` isn't recognized, switch the import to `package:flutter/material.dart`.

- [ ] **Step 4: Run all tests**

```
flutter test
```

Expected: 31 tests pass. The new `bgSyncOnStart` body is not unit-tested (platform-bound), but it must compile.

- [ ] **Step 5: Commit**

```
rtk git add clinic_mobile_app/lib/services/background_sync_service.dart
rtk git commit -m "feat(mobile-bt): sync-isolate onStart wires ConnectivitySyncService"
```

---

## Task 4: Wire `BackgroundSyncService` into `AppState`

Replace the three direct `_connectivity.startBluetoothAutoLoop()` call sites in `AppState` (lines 133, 144, 198) and the two `stopBluetoothAutoLoop()` call sites (lines 123, 135, 149) with `BackgroundSyncService.start()` / `.stop()`. Route `syncViaBluetoothNow` through `_bgSync.forceSync()`.

**Files:**
- Modify: `clinic_mobile_app/lib/state/app_state.dart`

- [ ] **Step 1: Add the import**

After existing service imports near the top of `app_state.dart`:

```dart
import '../services/background_sync_service.dart';
```

- [ ] **Step 2: Declare the field and instantiate it in the constructor**

Add a field below the existing service fields (around line 33):

```dart
  late final BackgroundSyncService _bgSync;
```

In the `AppState` constructor body (just after `_connectivity = ConnectivitySyncService(...)`, around line 80):

```dart
    _bgSync = BackgroundSyncService.production();
```

- [ ] **Step 3: Replace direct Timer calls with `_bgSync` calls**

Five mechanical replacements:

| Location | Old | New |
|---|---|---|
| `setBtEnabled`, line 123 | `_connectivity.stopBluetoothAutoLoop();` | `await _bgSync.stop();` |
| `setBtEnabled`, line 133 | `_connectivity.startBluetoothAutoLoop();` | `await _bgSync.start();` |
| `setBtEnabled`, line 135 | `_connectivity.stopBluetoothAutoLoop();` | `await _bgSync.stop();` |
| `bindBtPeer`, line 144 | `if (_btEnabled) _connectivity.startBluetoothAutoLoop();` | `if (_btEnabled) await _bgSync.start();` |
| `unbindBtPeer`, line 149 | `_connectivity.stopBluetoothAutoLoop();` | `await _bgSync.stop();` |
| `init`, line 198 | `_connectivity.startBluetoothAutoLoop();` | `await _bgSync.start();` |

Note: `setBtEnabled`, `bindBtPeer`, `unbindBtPeer`, and `init` are already `async` — adding `await` is mechanical. No signature changes.

- [ ] **Step 4: Rewrite `syncViaBluetoothNow` to use forceSync**

Replace the body of `syncViaBluetoothNow()` (lines 158–176) with:

```dart
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
      onTimeout: () { sub.cancel(); return false; },
    );
    await _loadBtState(); // pull updated lastSyncAt / lastError from storage
    return ok;
  }
```

- [ ] **Step 5: Run analyzer + tests**

```
cd clinic_mobile_app
flutter analyze
flutter test
```

Expected: analyzer clean, all 31 tests pass.

- [ ] **Step 6: Commit**

```
rtk git add clinic_mobile_app/lib/state/app_state.dart
rtk git commit -m "feat(mobile-bt): route BT auto-loop through BackgroundSyncService"
```

---

## Task 5: Refresh BT state on app resume (WidgetsBindingObserver)

When the user backgrounds the app, the sync isolate keeps writing `bt_last_sync_at` to storage on every successful tick. When they re-foreground the app, the UI's `AppState._btLastSyncAt` is stale — it still holds whatever was loaded at `init()`. Hook `WidgetsBindingObserver.didChangeAppLifecycleState` to refresh.

**Files:**
- Modify: `clinic_mobile_app/lib/state/app_state.dart`

- [ ] **Step 1: Make `AppState` extend `WidgetsBindingObserver`**

Change the class declaration (line 19):

```dart
class AppState extends ChangeNotifier with WidgetsBindingObserver {
```

- [ ] **Step 2: Register/unregister the observer**

In the constructor (after the existing service wiring, ~line 81):

```dart
    WidgetsBinding.instance.addObserver(this);
```

In `dispose()` (line 258, before `_connectivity.dispose()`):

```dart
    WidgetsBinding.instance.removeObserver(this);
```

- [ ] **Step 3: Override `didChangeAppLifecycleState`**

Add this method to `AppState` (anywhere — convention is below `dispose`):

```dart
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // Sync isolate may have updated bt_last_sync_at / bt_last_error
      // while we were backgrounded. Pull fresh values into UI state.
      unawaited(_loadBtState());
    }
  }
```

- [ ] **Step 4: Add the required `flutter/widgets.dart` import**

If not already imported via `material.dart`, ensure:

```dart
import 'package:flutter/widgets.dart';
```

is present at the top of `app_state.dart`. (It's likely already pulled in via `material.dart`.)

- [ ] **Step 5: Run analyzer + tests**

```
flutter analyze
flutter test
```

Expected: clean.

- [ ] **Step 6: Commit**

```
rtk git add clinic_mobile_app/lib/state/app_state.dart
rtk git commit -m "feat(mobile-bt): refresh BT last-sync display on app resume"
```

---

## Task 6: Collapse Settings BT Sync card to the three-state UX

The card today (settings_screen.dart, around line 340–425) has: enable toggle + peer picker + error banner + status line + a full-width "Sync now via Bluetooth" button. Replace with three states: **Off** (enable toggle), **Active** (peer label · last-sync line · advanced expander), **Syncing now** (transient spinner — driven by `app.btLastSyncAt` recency + listening to `_bgSync.onSyncFinished`).

The "Sync now" button stays — moved inside an `ExpansionTile` titled "Advanced" so it's no longer the headline action.

**Files:**
- Modify: `clinic_mobile_app/lib/screens/settings_screen.dart:350-425`

- [ ] **Step 1: Read the current card structure**

Open `settings_screen.dart` and locate the section starting around line 340 (the `Consumer<AppState>` that builds the BT card body). Identify:
- The `SwitchListTile.adaptive` for `app.btEnabled` (line 355)
- The bonded-peer `ListTile` / pick-button block (lines 364–380)
- The error banner / status line block (lines 381–409)
- The "Sync now via Bluetooth" `GradientButton` block (lines 410–420)

- [ ] **Step 2: Replace the card body with the three-state layout**

Replace lines 352–422 (the `Column` returned by `builder`) with:

```dart
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
                        if (app.btEnabled) ...[
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
                            Text(
                              app.locale == 'ar'
                                  ? 'نشِط · ${_btStatusLine(app)}'
                                  : 'Active · ${_btStatusLine(app)}',
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          ],
                          if (app.btBondedMac != null) ...[
                            const SizedBox(height: 8),
                            ExpansionTile(
                              tilePadding: EdgeInsets.zero,
                              childrenPadding: EdgeInsets.zero,
                              title: Text(
                                app.locale == 'ar' ? 'متقدم' : 'Advanced',
                                style: Theme.of(context).textTheme.bodyMedium,
                              ),
                              children: [
                                TextButton.icon(
                                  icon: const Icon(Icons.bluetooth_connected_rounded),
                                  label: Text(app.locale == 'ar'
                                      ? 'مزامنة الآن عبر بلوتوث'
                                      : 'Sync now via Bluetooth'),
                                  onPressed: () => _syncBtNow(context, app),
                                ),
                              ],
                            ),
                          ],
                        ],
                      ],
                    );
```

The key changes:
- Everything past the enable toggle is now wrapped in `if (app.btEnabled) ...[ ... ]` — when off, only the toggle is shown.
- The status line shows `Active · last sync N min ago` (the new prefix).
- The "Sync now" button is now inside an `ExpansionTile` titled "Advanced", smaller, and a `TextButton.icon` instead of a full-width `GradientButton`.

- [ ] **Step 3: Run analyzer**

```
cd clinic_mobile_app
flutter analyze
```

Expected: clean.

- [ ] **Step 4: Run tests + manual visual check via `flutter run`**

```
flutter test
# Optional but recommended: connect a device or emulator, then
flutter run
# Navigate to Settings → Bluetooth Sync. Toggle off — only the switch should remain.
# Toggle on (with permission grant) — peer picker, status line, Advanced expander appear.
# Expand Advanced — "Sync now via Bluetooth" button is there as a text button.
```

- [ ] **Step 5: Commit**

```
rtk git add clinic_mobile_app/lib/screens/settings_screen.dart
rtk git commit -m "feat(mobile-bt): three-state BT sync card; Sync now demoted to Advanced"
```

---

## Task 7: README update + hardware smoke checklist

Document the new behavior in README. Then run the hardware smoke (this is the gate that was already on the v1.0.0 punch list — now expanded with three background-tick scenarios).

**Files:**
- Modify: `README.md` (mobile blurb at line 30; Files section at lines 270–283; add a known-limitation note in the BT section).

- [ ] **Step 1: Update the mobile blurb at README line 30**

Locate the sentence in the Mobile blurb that ends with `...the same list the follow-up sheet picks from to prefill price/lab. The mobile app intentionally skips...`. Insert before that closing tail clause:

```
Bluetooth sync runs in a low-importance Android foreground service ("Clinic sync active" notification) so the 30-second auto-fallback loop keeps ticking while the app is in the doctor's pocket — walking into BT range of the bonded clinic PC while offline triggers a silent auto-pair (first time) then sync, no taps.
```

- [ ] **Step 2: Add `background_sync_service.dart` to the services file-tree (around line 282)**

After the `catalog_service.dart` line, before `report_service.dart`, add:

```
        │   ├── background_sync_service.dart  # Foreground-service wrapper: hosts the 30 s BT auto-loop in a background isolate so walk-by sync works when the app is backgrounded
```

- [ ] **Step 3: Add a known-limitation note**

Find the Tests section / parity invariants area (around line 470). Append after the existing parity-invariants paragraph:

```
**Known limitations (walk-by Bluetooth autosync):** the background service stays alive on stock Android via a low-importance foreground notification; on aggressive OEMs (Xiaomi MIUI, Huawei EMUI, Samsung One UI battery-optimization) the service may be killed when the app is swiped from recents — re-opening the app restarts it. Phone reboot also stops the service until the doctor opens the app once. Both are acceptable for the single-doctor clinic flow.
```

- [ ] **Step 4: Run the hardware smoke**

This requires a real Android phone OS-bonded to the Windows host, with `dental_clinic.py` running and the BT-SPP COM port enabled. Mark each scenario as it passes:

- [ ] **7.1 Backgrounded tick**: open app, send to recents, leave for 5 min. Tail server logs for `_bt_handle_request` / `paired_devices` activity. **PASS** if `bt_last_sync_at` advances at least 8 times in 5 min.
- [ ] **7.2 First-time walk-by**: fresh install, OS-bond, open app once (service starts), background, Wi-Fi+cellular off, sit next to PC. **PASS** if within 60s server log shows `op:bt_pair` then `sync_export`/`sync_import`. New row in `paired_devices`.
- [ ] **7.3 Subsequent walk-by**: same as 7.2 with token already issued. **PASS** if no `bt_pair`, just `sync_export`/`sync_import`. Round-trip <10s.
- [ ] **7.4 Settings change while backgrounded**: change BT peer in UI, send to recents. **PASS** if next tick uses new peer (verify via `paired_devices.device_id`).
- [ ] **7.5 Foreground notification**: visible after start, low-importance (no sound/vibrate), dismissible, reappears on next service start.
- [ ] **7.6 Token revoke self-heal**: while backgrounded, delete `paired_devices` row on server. **PASS** if next tick: `unauthorized` → automatic re-pair → sync continues.

- [ ] **Step 5: Final analyzer + tests**

```
cd clinic_mobile_app
flutter analyze
flutter test
cd ..
rtk proxy python -m pytest tests/
```

Expected: flutter analyze clean, ~31 flutter tests pass, 157 pytest pass.

- [ ] **Step 6: Commit**

```
rtk git add README.md
rtk git commit -m "docs(readme): walk-by BT autosync behavior + known limitations"
```

- [ ] **Step 7: Push**

```
rtk git push
```

---

## Self-Review Notes (post-write)

**Spec coverage check** — every section of the spec has a task:
- §Architecture/Isolate split → Task 3 (sync isolate onStart)
- §BackgroundSyncService wrapper → Task 2
- §UI surface → Task 7
- §Boundary crossings (force_sync) → Task 3 (server side) + Task 4 (client side)
- §DB concurrency → no task needed (WAL is default in sqflite, no code change)
- §Files (new + modified) → distributed across Tasks 1–7
- §Edge cases → handled by reused existing code (BluetoothSyncService self-heal etc.)
- §Testing/unit → Task 2 (4 unit tests); §Testing/hardware smoke → Task 7.1–7.6
- §Out of scope → documented in README via Task 7.3 known-limitations note

**Cross-task type consistency:** Method names match across tasks — `start`, `stop`, `forceSync`, `onSyncFinished` on `BackgroundSyncService`; `forceTick` on `ConnectivitySyncService`. `BgServiceClient` interface stable from Task 2 → Task 4. AppState's `_bgSync` field name consistent.

**No placeholders:** every step has either real code or a real command. No TBDs.

**Known follow-ups (NOT in this plan):**
- BOOT_COMPLETED auto-restart (deferred per spec)
- OEM battery-saver allowlist UX (deferred per spec)
- Cross-isolate "Syncing now…" spinner in real-time (current plan uses `onSyncFinished` only; `sync_started` events are not emitted by the sync isolate — added if user feedback demands it)
