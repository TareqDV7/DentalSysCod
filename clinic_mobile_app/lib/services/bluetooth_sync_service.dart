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
typedef SinceLoader = Future<String?> Function();
typedef OnExportHandler = Future<void> Function(Map<String, dynamic> exported);
typedef PushPayloadBuilder = Future<Map<String, dynamic>> Function();
typedef OnPushAckedHandler = Future<void> Function(
    Map<String, dynamic> pushedPayload);

/// One-shot Bluetooth sync runner. The 30-s cadence loop lives in
/// ConnectivitySyncService; this class just runs one cycle when called.
class BluetoothSyncService {
  final BtStreamOpener _open;
  final DeviceTokenLoader _loadToken;
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
    OnPushAckedHandler? onPushAcked,
  })  : _open = open,
        _loadToken = loadToken,
        _loadSince = loadSince,
        _onExport = onExport,
        _buildPush = buildPush,
        _onPushAcked = onPushAcked,
        _clientVersion = clientVersion;

  factory BluetoothSyncService.production({
    required DeviceTokenLoader deviceTokenLoader,
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
    OnPushAckedHandler? onPushAcked,
  }) =>
      BluetoothSyncService._(
        open: streamOpener,
        loadToken: deviceTokenLoader,
        loadSince: sinceLoader,
        onExport: onExport,
        buildPush: buildPushPayload,
        onPushAcked: onPushAcked,
        clientVersion: clientVersion,
      );

  Future<BtSessionResult> runOneSyncCycle(String bondedMac) async {
    final token = await _loadToken();
    if (token == null || token.isEmpty) {
      return const BtSessionResult.failure('no device token');
    }
    final BtStream stream;
    try {
      stream = await _open(bondedMac);
    } catch (e) {
      return BtSessionResult.failure(e.toString());
    }
    final client = BtSessionClient(stream);
    return client.runSession(
      deviceToken: token,
      clientVersion: _clientVersion,
      getSince: _loadSince,
      onExport: _onExport,
      buildPushPayload: _buildPush,
      onPushAcked: _onPushAcked,
    );
  }
}
