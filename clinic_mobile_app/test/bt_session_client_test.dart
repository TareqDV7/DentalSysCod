import 'dart:async';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/bluetooth_frame_codec.dart';
import 'package:clinic_mobile_app/services/bt_session_client.dart';

class _FakeBtStream implements BtStream {
  final _incoming = StreamController<Uint8List>();
  final List<List<int>> written = [];
  bool closed = false;
  @override
  Stream<Uint8List> get input => _incoming.stream;
  @override
  void writeBytes(List<int> bytes) => written.add(bytes);
  @override
  Future<void> close() async {
    closed = true;
    await _incoming.close();
  }
  void deliver(Map<String, dynamic> resp) {
    _incoming.add(BluetoothFrameCodec.encode(resp));
  }
}

void main() {
  test('successful hello -> export -> import round trip', () async {
    final stream = _FakeBtStream();
    final client = BtSessionClient(stream);
    final fut = client.runSession(
      deviceToken: 'good',
      clientVersion: '1.0.0',
      getSince: () async => null,
      onExport: (exported) async {},
      buildPushPayload: () async => {'tables': {}, 'tombstones': []},
    );
    await Future.delayed(Duration.zero);
    stream.deliver({'ok': true, 'server_version': '1.0.0'});
    await Future.delayed(Duration.zero);
    stream.deliver({'ok': true, 'tables': {}, 'tombstones': [], 'generated_at': 't'});
    await Future.delayed(Duration.zero);
    stream.deliver({'ok': true, 'applied': 0, 'skipped': 0});
    final result = await fut;
    expect(result.success, true);
    expect(stream.closed, true);
  });

  test('unauthorized response aborts and reports auth failure', () async {
    final stream = _FakeBtStream();
    final client = BtSessionClient(stream);
    final fut = client.runSession(
      deviceToken: 'bad',
      clientVersion: '1.0.0',
      getSince: () async => null,
      onExport: (_) async {},
      buildPushPayload: () async => {'tables': {}, 'tombstones': []},
    );
    await Future.delayed(Duration.zero);
    stream.deliver({'error': 'unauthorized'});
    final result = await fut;
    expect(result.success, false);
    expect(result.unauthorized, true);
  });

  test('error in import response is reported as failure but not unauthorized',
      () async {
    final stream = _FakeBtStream();
    final client = BtSessionClient(stream);
    final fut = client.runSession(
      deviceToken: 'good',
      clientVersion: '1.0.0',
      getSince: () async => null,
      onExport: (_) async {},
      buildPushPayload: () async => {'tables': {}, 'tombstones': []},
    );
    await Future.delayed(Duration.zero);
    stream.deliver({'ok': true, 'server_version': '1.0.0'});
    await Future.delayed(Duration.zero);
    stream.deliver({'ok': true, 'tables': {}, 'tombstones': []});
    await Future.delayed(Duration.zero);
    stream.deliver({'error': 'malformed frame'});
    final result = await fut;
    expect(result.success, false);
    expect(result.unauthorized, false);
  });
}
