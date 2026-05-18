import 'dart:async';
import 'dart:typed_data';

import 'bluetooth_frame_codec.dart';

/// Tiny abstraction over the underlying BT connection so tests can swap in a
/// fake without dragging in flutter_bluetooth_serial.
abstract class BtStream {
  Stream<Uint8List> get input;
  void writeBytes(List<int> bytes);
  Future<void> close();
}

/// Outcome of one Bluetooth sync round-trip.
class BtSessionResult {
  final bool success;
  final bool unauthorized;
  final String? errorMessage;
  const BtSessionResult.ok()
      : success = true, unauthorized = false, errorMessage = null;
  const BtSessionResult.unauthorized()
      : success = false, unauthorized = true, errorMessage = 'unauthorized';
  const BtSessionResult.failure(this.errorMessage)
      : success = false, unauthorized = false;
}

/// Outcome of one Bluetooth auto-pair handshake (`op:bt_pair`).
class BtPairingResult {
  final bool success;
  final String? deviceToken;
  final String? errorMessage;
  const BtPairingResult.ok(String token)
      : success = true, deviceToken = token, errorMessage = null;
  const BtPairingResult.failure(this.errorMessage)
      : success = false, deviceToken = null;
}

/// Runs one hello → sync_export → sync_import dialogue over the supplied stream.
class BtSessionClient {
  final BtStream _stream;
  BtSessionClient(this._stream);

  Future<BtSessionResult> runSession({
    required String deviceToken,
    required String clientVersion,
    required Future<String?> Function() getSince,
    required Future<void> Function(Map<String, dynamic> exported) onExport,
    required Future<Map<String, dynamic>> Function() buildPushPayload,
    Future<void> Function(Map<String, dynamic> pushedPayload)? onPushAcked,
    Duration handshakeTimeout = const Duration(seconds: 10),
  }) async {
    final reader = FrameReader();
    final responses = StreamController<Map<String, dynamic>>.broadcast();
    late StreamSubscription<Uint8List> sub;
    sub = _stream.input.listen(
      (chunk) {
        reader.addBytes(chunk);
        while (true) {
          try {
            final frame = reader.next();
            if (frame == null) break;
            responses.add(frame);
          } on FormatException catch (e) {
            responses.addError(e);
            break;
          }
        }
      },
      onError: responses.addError,
      onDone: () => responses.close(),
      cancelOnError: false,
    );

    Future<Map<String, dynamic>> awaitOne() async {
      final r = await responses.stream.first.timeout(handshakeTimeout);
      return r;
    }

    Future<void> send(Map<String, dynamic> msg) async {
      _stream.writeBytes(BluetoothFrameCodec.encode(msg));
    }

    Future<BtSessionResult> finishWith(BtSessionResult r) async {
      await sub.cancel();
      await responses.close();
      await _stream.close();
      return r;
    }

    try {
      await send({
        'op': 'hello',
        'device_token': deviceToken,
        'client_version': clientVersion,
      });
      final hello = await awaitOne();
      if (hello['error'] == 'unauthorized') {
        return finishWith(const BtSessionResult.unauthorized());
      }
      if (hello['ok'] != true) {
        return finishWith(BtSessionResult.failure('hello failed: $hello'));
      }

      final since = await getSince();
      await send({'op': 'sync_export', 'since': since});
      final exportResp = await awaitOne();
      if (exportResp['error'] != null) {
        return finishWith(BtSessionResult.failure(exportResp['error'].toString()));
      }
      await onExport(exportResp);

      final push = await buildPushPayload();
      await send({'op': 'sync_import', 'tables': push['tables'], 'tombstones': push['tombstones']});
      final importResp = await awaitOne();
      if (importResp['error'] != null) {
        return finishWith(BtSessionResult.failure(importResp['error'].toString()));
      }
      if (onPushAcked != null) {
        try {
          await onPushAcked(push);
        } catch (_) {
          // A bookkeeping failure (mark-synced) shouldn't tank the whole
          // session — the peer already accepted the import. Next cycle's
          // unsynced query will simply re-push the same rows.
        }
      }

      return finishWith(const BtSessionResult.ok());
    } on TimeoutException {
      return finishWith(BtSessionResult.failure('timeout'));
    } catch (e) {
      return finishWith(BtSessionResult.failure(e.toString()));
    }
  }

  /// One-shot `op:bt_pair` handshake. Sends device_id/device_name over the
  /// already-OS-Bluetooth-bonded channel; server creates (or rotates) a
  /// paired_devices row and returns a fresh device_token. The stream is
  /// closed when this returns — callers should open a new one for the
  /// subsequent sync session.
  Future<BtPairingResult> runPairing({
    required String deviceId,
    required String deviceName,
    required String clientVersion,
    Duration timeout = const Duration(seconds: 10),
  }) async {
    final reader = FrameReader();
    final responses = StreamController<Map<String, dynamic>>.broadcast();
    late StreamSubscription<Uint8List> sub;
    sub = _stream.input.listen(
      (chunk) {
        reader.addBytes(chunk);
        while (true) {
          try {
            final frame = reader.next();
            if (frame == null) break;
            responses.add(frame);
          } on FormatException catch (e) {
            responses.addError(e);
            break;
          }
        }
      },
      onError: responses.addError,
      onDone: () => responses.close(),
      cancelOnError: false,
    );

    Future<BtPairingResult> finishWith(BtPairingResult r) async {
      await sub.cancel();
      await responses.close();
      await _stream.close();
      return r;
    }

    try {
      _stream.writeBytes(BluetoothFrameCodec.encode({
        'op': 'bt_pair',
        'device_id': deviceId,
        'device_name': deviceName,
        'client_version': clientVersion,
      }));
      final resp = await responses.stream.first.timeout(timeout);
      final err = resp['error'];
      if (err != null) {
        return finishWith(BtPairingResult.failure(err.toString()));
      }
      final token = resp['device_token']?.toString();
      if (token == null || token.isEmpty) {
        return finishWith(
            BtPairingResult.failure('pair response missing device_token'));
      }
      return finishWith(BtPairingResult.ok(token));
    } on TimeoutException {
      return finishWith(BtPairingResult.failure('timeout'));
    } catch (e) {
      return finishWith(BtPairingResult.failure(e.toString()));
    }
  }
}
