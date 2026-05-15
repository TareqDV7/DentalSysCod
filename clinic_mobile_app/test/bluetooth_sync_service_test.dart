import 'dart:async';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/bluetooth_frame_codec.dart';
import 'package:clinic_mobile_app/services/bt_session_client.dart';
import 'package:clinic_mobile_app/services/bluetooth_sync_service.dart';

class _ScriptedStream implements BtStream {
  final _in = StreamController<Uint8List>();
  final List<List<int>> writes = [];
  bool closed = false;
  final List<Map<String, dynamic>> _script;
  _ScriptedStream(this._script);
  @override
  Stream<Uint8List> get input => _in.stream;
  @override
  void writeBytes(List<int> bytes) {
    writes.add(bytes);
    if (_script.isNotEmpty) {
      final resp = _script.removeAt(0);
      Future.microtask(() => _in.add(BluetoothFrameCodec.encode(resp)));
    }
  }
  @override
  Future<void> close() async { closed = true; await _in.close(); }
}

void main() {
  test('runOneSyncCycle returns success on full round trip', () async {
    final stream = _ScriptedStream([
      {'ok': true, 'server_version': '1.0.0'},
      {'ok': true, 'tables': {}, 'tombstones': [], 'generated_at': 't'},
      {'ok': true, 'applied': 0, 'skipped': 0},
    ]);
    final svc = BluetoothSyncService.forTest(
      streamOpener: (mac) async => stream,
      deviceTokenLoader: () async => 'good',
      sinceLoader: () async => null,
      onExport: (_) async {},
      buildPushPayload: () async => {'tables': {}, 'tombstones': []},
      clientVersion: '1.0.0',
    );
    final result = await svc.runOneSyncCycle('00:11:22:33:44:55');
    expect(result.success, true);
    expect(stream.closed, true);
  });

  test('runOneSyncCycle reports unauthorized and stops loop', () async {
    final stream = _ScriptedStream([{'error': 'unauthorized'}]);
    final svc = BluetoothSyncService.forTest(
      streamOpener: (mac) async => stream,
      deviceTokenLoader: () async => 'bad',
      sinceLoader: () async => null,
      onExport: (_) async {},
      buildPushPayload: () async => {'tables': {}, 'tombstones': []},
      clientVersion: '1.0.0',
    );
    final result = await svc.runOneSyncCycle('00:11:22:33:44:55');
    expect(result.success, false);
    expect(result.unauthorized, true);
  });

  test('returns failure when opener throws (peer out of range)', () async {
    final svc = BluetoothSyncService.forTest(
      streamOpener: (_) async => throw 'cannot connect',
      deviceTokenLoader: () async => 'good',
      sinceLoader: () async => null,
      onExport: (_) async {},
      buildPushPayload: () async => {'tables': {}, 'tombstones': []},
      clientVersion: '1.0.0',
    );
    final result = await svc.runOneSyncCycle('00:11:22:33:44:55');
    expect(result.success, false);
    expect(result.unauthorized, false);
  });
}
