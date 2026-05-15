import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/bluetooth_frame_codec.dart';

void main() {
  group('BluetoothFrameCodec', () {
    test('round trip', () {
      final payload = {'op': 'hello', 'device_token': 'abc'};
      final framed = BluetoothFrameCodec.encode(payload);
      final reader = FrameReader();
      reader.addBytes(framed);
      expect(reader.next(), payload);
    });

    test('4-byte big-endian length prefix', () {
      final framed = BluetoothFrameCodec.encode({'op': 'ping'});
      final body = utf8.encode(jsonEncode({'op': 'ping'}));
      expect(framed.length, 4 + body.length);
      final lengthHeader =
          ByteData.sublistView(framed, 0, 4).getUint32(0, Endian.big);
      expect(lengthHeader, body.length);
    });

    test('handles unicode payload', () {
      final payload = {'clinic_name': 'عيادة الأسنان', 'note': '中文'};
      final framed = BluetoothFrameCodec.encode(payload);
      final reader = FrameReader();
      reader.addBytes(framed);
      expect(reader.next(), payload);
    });

    test('decodes back-to-back frames', () {
      final f1 = BluetoothFrameCodec.encode({'a': 1});
      final f2 = BluetoothFrameCodec.encode({'b': 2});
      final reader = FrameReader();
      reader.addBytes(Uint8List.fromList([...f1, ...f2]));
      expect(reader.next(), {'a': 1});
      expect(reader.next(), {'b': 2});
      expect(reader.next(), isNull);
    });

    test('reader returns null when frame is partial', () {
      final framed = BluetoothFrameCodec.encode({'a': 1});
      final reader = FrameReader();
      reader.addBytes(framed.sublist(0, 3));   // only 3 of 4 length bytes
      expect(reader.next(), isNull);
      reader.addBytes(framed.sublist(3));      // feed the rest
      expect(reader.next(), {'a': 1});
    });

    test('encode rejects oversized payload', () {
      final huge = {'data': 'x' * (4 * 1024 * 1024)};   // ~4 MB
      expect(() => BluetoothFrameCodec.encode(huge), throwsArgumentError);
    });
  });
}
