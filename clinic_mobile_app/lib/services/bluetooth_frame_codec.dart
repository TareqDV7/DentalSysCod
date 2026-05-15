import 'dart:convert';
import 'dart:typed_data';

/// 4-byte big-endian length prefix + UTF-8 JSON payload.
class BluetoothFrameCodec {
  static const int maxFrameBytes = 4 * 1024 * 1024;

  static Uint8List encode(Map<String, dynamic> payload) {
    final body = utf8.encode(jsonEncode(payload));
    if (body.length > maxFrameBytes) {
      throw ArgumentError('frame too large: ${body.length} > $maxFrameBytes');
    }
    final out = BytesBuilder();
    final header = ByteData(4)..setUint32(0, body.length, Endian.big);
    out.add(header.buffer.asUint8List());
    out.add(body);
    return out.toBytes();
  }
}

/// Incremental decoder: feed bytes as they arrive, call [next] to pull
/// completed frames out. Returns null when no full frame is buffered yet.
class FrameReader {
  final BytesBuilder _buf = BytesBuilder(copy: false);

  void addBytes(List<int> bytes) {
    _buf.add(bytes);
  }

  Map<String, dynamic>? next() {
    final all = _buf.toBytes();
    if (all.length < 4) return null;
    final length = ByteData.sublistView(all, 0, 4).getUint32(0, Endian.big);
    if (length > BluetoothFrameCodec.maxFrameBytes) {
      throw const FormatException('frame too large');
    }
    if (all.length < 4 + length) return null;
    final body = all.sublist(4, 4 + length);
    final rest = all.sublist(4 + length);
    _buf.clear();
    _buf.add(rest);
    final decoded = jsonDecode(utf8.decode(body));
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('frame body is not a JSON object');
    }
    return decoded;
  }
}
