import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';

import 'package:clinic_mobile_app/services/clinic_api.dart';
import 'package:clinic_mobile_app/services/post_studio_bridge_handler.dart';

class _FakeClinicApi extends ClinicApi {
  List<dynamic> getListReturn = <dynamic>[];
  Map<String, dynamic> getReturn = <String, dynamic>{};
  Map<String, dynamic> postMultipartReturn = {'id': 1};
  Map<String, String>? lastFields;
  String? lastFilePath;
  String? lastGetPath;
  String? lastDeletePath;

  @override
  Future<List<dynamic>> getList(String path, {Map<String, dynamic>? query}) async {
    lastGetPath = path;
    return getListReturn;
  }

  @override
  Future<Map<String, dynamic>> get(String path, {Map<String, dynamic>? query}) async {
    lastGetPath = path;
    return getReturn;
  }

  @override
  Future<void> delete(String path, {Map<String, dynamic>? query}) async {
    lastDeletePath = path;
  }

  @override
  Future<Map<String, dynamic>> postMultipart(
    String path, {
    required Map<String, String> fields,
    required String fileField,
    required String filePath,
    String? fileName,
  }) async {
    lastFields = fields;
    lastFilePath = filePath;
    return postMultipartReturn;
  }
}

class _ThrowingClinicApi extends ClinicApi {
  @override
  Future<List<dynamic>> getList(String path, {Map<String, dynamic>? query}) async {
    throw Exception('network down');
  }
}

void main() {
  group('PostStudioBridgeHandler.onMessage', () {
    test('listPosts passes through to ClinicApi.getList and resolves with the result',
        () async {
      final calls = <String>[];
      final api = _FakeClinicApi()
        ..getListReturn = [
          {'id': 1, 'theme': 'dark_premium'},
        ];
      final handler = PostStudioBridgeHandler(
        api: api,
        runJavaScript: (js) async => calls.add(js),
      );
      await handler.onMessage(jsonEncode({'id': '1', 'method': 'listPosts', 'args': null}));
      expect(api.lastGetPath, '/api/posts');
      expect(calls, [
        'window.__psResolve(${jsonEncode('1')}, '
            '${jsonEncode(jsonEncode([
                  {'id': 1, 'theme': 'dark_premium'}
                ]))})',
      ]);
    });

    test('getPost passes through to ClinicApi.get with the id in the path', () async {
      final calls = <String>[];
      final api = _FakeClinicApi()..getReturn = {'id': 7, 'theme': 'bold'};
      final handler = PostStudioBridgeHandler(
        api: api,
        runJavaScript: (js) async => calls.add(js),
      );
      await handler.onMessage(jsonEncode({
        'id': '2',
        'method': 'getPost',
        'args': {'id': 7},
      }));
      expect(api.lastGetPath, '/api/posts/7');
      expect(calls.single, contains('"id":7'));
    });

    test('deletePost passes through to ClinicApi.delete with the id in the path', () async {
      final calls = <String>[];
      final api = _FakeClinicApi();
      final handler = PostStudioBridgeHandler(
        api: api,
        runJavaScript: (js) async => calls.add(js),
      );
      await handler.onMessage(jsonEncode({
        'id': '3',
        'method': 'deletePost',
        'args': {'id': 9},
      }));
      expect(api.lastDeletePath, '/api/posts/9');
      expect(calls.single, 'window.__psResolve(${jsonEncode('3')}, ${jsonEncode('null')})');
    });

    test('pickPhotos returns base64 data URLs for each picked file', () async {
      final calls = <String>[];
      final handler = PostStudioBridgeHandler(
        api: _FakeClinicApi(),
        runJavaScript: (js) async => calls.add(js),
        pickImages: () async => [
          XFile.fromData(Uint8List.fromList([1, 2, 3]),
              mimeType: 'image/jpeg', name: 'a.jpg'),
        ],
      );
      await handler.onMessage(jsonEncode({'id': '4', 'method': 'pickPhotos', 'args': null}));
      expect(
        calls.single,
        'window.__psResolve(${jsonEncode('4')}, '
            '${jsonEncode(jsonEncode([
                  {'id': 'a.jpg', 'dataUrl': 'data:image/jpeg;base64,AQID'}
                ]))})',
      );
    });

    test('pickPhotos resolves with an empty list when the picker is cancelled', () async {
      final calls = <String>[];
      final handler = PostStudioBridgeHandler(
        api: _FakeClinicApi(),
        runJavaScript: (js) async => calls.add(js),
        pickImages: () async => [],
      );
      await handler.onMessage(jsonEncode({'id': '5', 'method': 'pickPhotos', 'args': null}));
      expect(calls.single, 'window.__psResolve(${jsonEncode('5')}, ${jsonEncode('[]')})');
    });

    test('savePost decodes the PNG, writes a temp file, and posts the right fields',
        () async {
      final calls = <String>[];
      final api = _FakeClinicApi()..postMultipartReturn = {'id': 42};
      Uint8List? capturedBytes;
      final handler = PostStudioBridgeHandler(
        api: api,
        runJavaScript: (js) async => calls.add(js),
        writeTempPng: (bytes) async {
          capturedBytes = bytes;
          return '/tmp/fake.png';
        },
      );
      await handler.onMessage(jsonEncode({
        'id': '6',
        'method': 'savePost',
        'args': {
          'pngB64': base64Encode([1, 2, 3]),
          'templateJson': '{"theme":"dark_premium"}',
          'meta': {'theme': 'dark_premium', 'size': 'square', 'title': 'Veneers'},
        },
      }));
      expect(capturedBytes, [1, 2, 3]);
      expect(api.lastFilePath, '/tmp/fake.png');
      expect(api.lastFields, {
        'template_json': '{"theme":"dark_premium"}',
        'theme': 'dark_premium',
        'size': 'square',
        'title': 'Veneers',
      });
      expect(calls.single,
          'window.__psResolve(${jsonEncode('6')}, ${jsonEncode(jsonEncode({'id': 42}))})');
    });

    test('an unknown method surfaces as a bridge rejection', () async {
      final calls = <String>[];
      final handler = PostStudioBridgeHandler(
        api: _FakeClinicApi(),
        runJavaScript: (js) async => calls.add(js),
      );
      await handler.onMessage(jsonEncode({'id': '7', 'method': 'bogus', 'args': null}));
      expect(calls.single, startsWith('window.__psReject('));
      expect(calls.single, contains('unknown bridge method'));
    });

    test('a thrown network error surfaces as a bridge rejection', () async {
      final calls = <String>[];
      final handler = PostStudioBridgeHandler(
        api: _ThrowingClinicApi(),
        runJavaScript: (js) async => calls.add(js),
      );
      await handler.onMessage(jsonEncode({'id': '8', 'method': 'listPosts', 'args': null}));
      expect(calls.single, startsWith('window.__psReject('));
      expect(calls.single, contains('network down'));
    });

    test('malformed JSON is ignored without throwing', () async {
      final calls = <String>[];
      final handler = PostStudioBridgeHandler(
        api: _FakeClinicApi(),
        runJavaScript: (js) async => calls.add(js),
      );
      await handler.onMessage('not json');
      expect(calls, isEmpty);
    });
  });
}
