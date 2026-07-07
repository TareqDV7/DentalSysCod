import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:image_picker/image_picker.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'clinic_api.dart';

/// Dart-side handler for the Post Studio JS<->Dart bridge (P6 mobile parity).
///
/// Registered as the `PostStudioBridge` JavaScriptChannel's message handler.
/// Routes each `{id, method, args}` frame the editor bundle sends and replies
/// by injecting `window.__psResolve(id, json)` / `window.__psReject(id, message)`
/// via [runJavaScript] — mirrors static/post_studio/host.js's
/// createMobileHost() bridge protocol exactly.
class PostStudioBridgeHandler {
  PostStudioBridgeHandler({
    required this.api,
    required this.runJavaScript,
    Future<List<XFile>> Function()? pickImages,
    Future<String> Function(Uint8List bytes)? writeTempPng,
  })  : _pickImages = pickImages ?? (() => ImagePicker().pickMultiImage()),
        _writeTempPng = writeTempPng ?? _defaultWriteTempPng;

  final ClinicApi api;
  final Future<void> Function(String script) runJavaScript;
  final Future<List<XFile>> Function() _pickImages;
  final Future<String> Function(Uint8List bytes) _writeTempPng;

  static const _endpoint = '/api/posts';

  static Future<String> _defaultWriteTempPng(Uint8List bytes) async {
    final dir = await getTemporaryDirectory();
    final path = p.join(
      dir.path,
      'post_studio_${DateTime.now().millisecondsSinceEpoch}.png',
    );
    await File(path).writeAsBytes(bytes, flush: true);
    return path;
  }

  /// Handles one `{id, method, args}` JSON frame from the JS side.
  Future<void> onMessage(String raw) async {
    final Map<String, dynamic> msg;
    try {
      msg = jsonDecode(raw) as Map<String, dynamic>;
    } on FormatException {
      return;
    }
    final id = msg['id'] as String;
    final method = msg['method'] as String?;
    try {
      final result = await _dispatch(method, msg['args']);
      await _resolve(id, result);
    } catch (e) {
      // Deliberately broader than `on Exception`: this is the outer boundary
      // of one JS<->Dart bridge frame. A malformed args shape from the JS
      // side can throw a bare Error (e.g. TypeError), and the JS-side
      // Promise must still settle via reject — or the editor UI hangs
      // forever waiting on a response that will never come.
      await _reject(id, e.toString());
    }
  }

  Future<dynamic> _dispatch(String? method, dynamic args) {
    switch (method) {
      case 'pickPhotos':
        return _pickPhotos();
      case 'savePost':
        return _savePost(Map<String, dynamic>.from(args as Map));
      case 'listPosts':
        return api.getList(_endpoint);
      case 'getPost':
        return api.get('$_endpoint/${(args as Map)['id']}');
      case 'deletePost':
        return api.delete('$_endpoint/${(args as Map)['id']}');
      default:
        throw Exception('unknown bridge method: $method');
    }
  }

  Future<List<Map<String, String>>> _pickPhotos() async {
    final files = await _pickImages();
    final out = <Map<String, String>>[];
    for (final f in files) {
      final bytes = await f.readAsBytes();
      final mime = f.mimeType ?? 'image/jpeg';
      out.add({'id': f.name, 'dataUrl': 'data:$mime;base64,${base64Encode(bytes)}'});
    }
    return out;
  }

  Future<Map<String, dynamic>> _savePost(Map<String, dynamic> args) async {
    final meta = Map<String, dynamic>.from(args['meta'] as Map? ?? {});
    final bytes = base64Decode(args['pngB64'] as String);
    final path = await _writeTempPng(bytes);
    return api.postMultipart(
      _endpoint,
      fields: {
        'template_json': args['templateJson'] as String,
        'theme': (meta['theme'] ?? '').toString(),
        'size': (meta['size'] ?? '').toString(),
        'title': (meta['title'] ?? '').toString(),
      },
      fileField: 'image',
      filePath: path,
    );
  }

  Future<void> _resolve(String id, dynamic result) {
    final js = 'window.__psResolve(${jsonEncode(id)}, ${jsonEncode(jsonEncode(result))})';
    return runJavaScript(js);
  }

  Future<void> _reject(String id, String message) {
    final js = 'window.__psReject(${jsonEncode(id)}, ${jsonEncode(message)})';
    return runJavaScript(js);
  }
}
