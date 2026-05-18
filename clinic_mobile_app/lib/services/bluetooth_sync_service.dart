import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_bluetooth_serial/flutter_bluetooth_serial.dart';

import 'bt_session_client.dart';

/// Wraps a `BluetoothConnection` so the protocol client can use it via the
/// `BtStream` abstraction.
class _BtConnectionStream implements BtStream {
  final BluetoothConnection _conn;
  _BtConnectionStream(this._conn);
  @override
  Stream<Uint8List> get input => _conn.input ?? const Stream<Uint8List>.empty();
  @override
  void writeBytes(List<int> bytes) {
    _conn.output.add(Uint8List.fromList(bytes));
  }
  @override
  Future<void> close() async {
    try { await _conn.output.allSent; } catch (_) {}
    try { await _conn.close(); } catch (_) {}
  }
}

typedef BtStreamOpener = Future<BtStream> Function(String mac);
typedef DeviceTokenLoader = Future<String?> Function();
typedef DeviceTokenSaver = Future<void> Function(String token);
typedef DeviceIdLoader = Future<String> Function();
typedef SinceLoader = Future<String?> Function();
typedef OnExportHandler = Future<void> Function(Map<String, dynamic> exported);
typedef PushPayloadBuilder = Future<Map<String, dynamic>> Function();
typedef OnPushAckedHandler = Future<void> Function(
    Map<String, dynamic> pushedPayload);

/// One-shot Bluetooth sync runner. The 30-s cadence loop lives in
/// ConnectivitySyncService; this class just runs one cycle when called.
///
/// When [_saveToken] and [_loadDeviceId] are wired (production wiring), the
/// service self-pairs over BT on first use and self-heals if the server's
/// token gets revoked — no 6-digit code required, the OS-level Bluetooth
/// bond is the trust gate.
class BluetoothSyncService {
  final BtStreamOpener _open;
  final DeviceTokenLoader _loadToken;
  final DeviceTokenSaver? _saveToken;
  final DeviceIdLoader? _loadDeviceId;
  final SinceLoader _loadSince;
  final OnExportHandler _onExport;
  final PushPayloadBuilder _buildPush;
  final OnPushAckedHandler? _onPushAcked;
  final String _clientVersion;

  BluetoothSyncService._({
    required BtStreamOpener open,
    required DeviceTokenLoader loadToken,
    required SinceLoader loadSince,
    required OnExportHandler onExport,
    required PushPayloadBuilder buildPush,
    required String clientVersion,
    DeviceTokenSaver? saveToken,
    DeviceIdLoader? loadDeviceId,
    OnPushAckedHandler? onPushAcked,
  })  : _open = open,
        _loadToken = loadToken,
        _saveToken = saveToken,
        _loadDeviceId = loadDeviceId,
        _loadSince = loadSince,
        _onExport = onExport,
        _buildPush = buildPush,
        _onPushAcked = onPushAcked,
        _clientVersion = clientVersion;

  factory BluetoothSyncService.production({
    required DeviceTokenLoader deviceTokenLoader,
    required DeviceTokenSaver deviceTokenSaver,
    required DeviceIdLoader deviceIdLoader,
    required SinceLoader sinceLoader,
    required OnExportHandler onExport,
    required PushPayloadBuilder buildPushPayload,
    required String clientVersion,
    OnPushAckedHandler? onPushAcked,
  }) {
    return BluetoothSyncService._(
      open: (mac) async {
        final conn = await BluetoothConnection.toAddress(mac)
            .timeout(const Duration(seconds: 10));
        return _BtConnectionStream(conn);
      },
      loadToken: deviceTokenLoader,
      saveToken: deviceTokenSaver,
      loadDeviceId: deviceIdLoader,
      loadSince: sinceLoader,
      onExport: onExport,
      buildPush: buildPushPayload,
      onPushAcked: onPushAcked,
      clientVersion: clientVersion,
    );
  }

  /// Test seam.
  factory BluetoothSyncService.forTest({
    required BtStreamOpener streamOpener,
    required DeviceTokenLoader deviceTokenLoader,
    required SinceLoader sinceLoader,
    required OnExportHandler onExport,
    required PushPayloadBuilder buildPushPayload,
    required String clientVersion,
    DeviceTokenSaver? deviceTokenSaver,
    DeviceIdLoader? deviceIdLoader,
    OnPushAckedHandler? onPushAcked,
  }) =>
      BluetoothSyncService._(
        open: streamOpener,
        loadToken: deviceTokenLoader,
        saveToken: deviceTokenSaver,
        loadDeviceId: deviceIdLoader,
        loadSince: sinceLoader,
        onExport: onExport,
        buildPush: buildPushPayload,
        onPushAcked: onPushAcked,
        clientVersion: clientVersion,
      );

  bool get _canAutoPair => _saveToken != null && _loadDeviceId != null;

  /// Open a fresh stream, run `op:bt_pair`, store the returned token.
  /// Returns the new token on success, or null on failure.
  Future<String?> _autoPair(String bondedMac) async {
    if (!_canAutoPair) return null;
    final BtStream stream;
    try {
      stream = await _open(bondedMac);
    } catch (_) {
      return null;
    }
    final deviceId = await _loadDeviceId!();
    final result = await BtSessionClient(stream).runPairing(
      deviceId: deviceId,
      deviceName: deviceId,
      clientVersion: _clientVersion,
    );
    if (!result.success || result.deviceToken == null) return null;
    await _saveToken!(result.deviceToken!);
    return result.deviceToken;
  }

  Future<BtSessionResult> _runSessionOnce(
      String bondedMac, String deviceToken) async {
    final BtStream stream;
    try {
      stream = await _open(bondedMac);
    } catch (e) {
      return BtSessionResult.failure(e.toString());
    }
    return BtSessionClient(stream).runSession(
      deviceToken: deviceToken,
      clientVersion: _clientVersion,
      getSince: _loadSince,
      onExport: _onExport,
      buildPushPayload: _buildPush,
      onPushAcked: _onPushAcked,
    );
  }

  Future<BtSessionResult> runOneSyncCycle(String bondedMac) async {
    var token = await _loadToken();

    // First-time onboarding over BT: no token stored → auto-pair using the
    // OS-bonded BT channel itself (no 6-digit code needed).
    if (token == null || token.isEmpty) {
      if (!_canAutoPair) {
        return const BtSessionResult.failure('no device token');
      }
      token = await _autoPair(bondedMac);
      if (token == null) {
        return const BtSessionResult.failure('bt pairing failed');
      }
    }

    final result = await _runSessionOnce(bondedMac, token);

    // Self-heal: stored token no longer recognised by the server (DB reset,
    // admin revoked the device). Drop it, re-pair, retry once.
    if (result.unauthorized && _canAutoPair) {
      await _saveToken!('');
      final fresh = await _autoPair(bondedMac);
      if (fresh == null) return result;
      return _runSessionOnce(bondedMac, fresh);
    }

    return result;
  }
}
