# Post Studio P6 — Mobile Editor Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mobile app's read-only `PostsScreen` gallery with the same client-side WYSIWYG editor bundle desktop uses, mounted in a Flutter WebView and bridged to the existing authed `ClinicApi`/`image_picker`, so mobile gets full create/edit parity with desktop.

**Architecture:** A new `createMobileHost()` in `static/post_studio/host.js` implements the same `PostStudioHost` shape as desktop's `createDesktopHost()`, but talks to Dart over a single JSON-RPC-style `JavaScriptChannel` (`PostStudioBridge`) instead of `fetch`. Dart's `PostStudioBridgeHandler` routes each `{id, method, args}` frame to `image_picker`/`ClinicApi` and replies by injecting `window.__psResolve`/`window.__psReject`. `editor.js` gains a `pointerProfile` option so touch hit-targets grow without touching desktop's shipped behavior.

**Tech Stack:** Pure-ESM JS modules under `static/post_studio/` (no bundler, no new JS runtime deps); `node --test` for host.js unit tests; Playwright (`--allow-file-access-from-files`) over `static/post_studio/spike/editor_harness.html` for editor.js behavior; Flutter/Dart with `webview_flutter` (new dependency) + existing `image_picker`/`path_provider`/`provider`; `flutter_test` for the bridge handler.

## Global Constraints

- Dart SDK floor: `^3.11.5` (unchanged, from `clinic_mobile_app/pubspec.yaml`).
- New dependency: `webview_flutter: ^4.14.0` (current latest stable as of this plan).
- No new backend endpoints — every Dart call reuses `/api/posts` exactly as desktop's `host.js` already does.
- Desktop's default `pointerProfile` (`'mouse'`) must stay byte-identical — the existing 16-test Playwright suite in `tests/e2e/test_editor_flow.py` must stay green unchanged.
- Bundled assets only: `static/post_studio/*.js` stays the single source of truth; `clinic_mobile_app/assets/post_studio/` holds synced copies (via `tools/sync_post_studio_mobile_assets.py`, run manually before any APK/IPA build after editing `editor.js`/`host.js`) plus the hand-written `mobile_editor.html`. No cross-repo Flutter asset paths.
- No mock framework (mockito/mocktail) is present in `pubspec.yaml` and none is added — Dart test doubles use plain subclass-override (`extends ClinicApi`) and constructor injection, matching this codebase's existing convention (see `medical_image_reconcile_test.dart`).
- `clinic_mobile_app/lib/**` imports stay relative (`import 'clinic_api.dart';`, `import '../models/x.dart';`), matching the existing convention throughout this package (not `package:` imports).
- PR remains HELD — do not open a PR or push to origin unprompted. P6 is the last phase of `feat/post-studio`.

---

## Task 1: `host.js` — `createMobileHost()`

**Files:**
- Modify: `static/post_studio/host.js` (currently 105 lines; add after `createDesktopHost`, ending ~line 105)
- Test: `tests/js/host.test.mjs`

**Interfaces:**
- Consumes: existing `fileToDataUrl` (module-private helper, host.js:16-23), `downscaleDataUrl(dataUrl, maxDim)` (host.js:33-48, exported), `MAX_PHOTO_DIM` (host.js:31, exported).
- Produces: `createMobileHost(bridge = globalThis.PostStudioBridge)` returning `{pickPhotos, savePost, listPosts, getPost, deletePost}` — the same `PostStudioHost` shape as `createDesktopHost()`. Also sets `globalThis.__psResolve(id, resultJson)` / `globalThis.__psReject(id, message)` (called by Dart's injected `runJavaScript`, which uses `window.__psResolve`/`window.__psReject` — identical objects since `window === globalThis` in a WebView). Task 3's Dart handler and Task 4's `mobile_editor.html` both call `createMobileHost()`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/js/host.test.mjs` with:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createDesktopHost, createMobileHost } from '../../static/post_studio/host.js';

test('createDesktopHost exposes the PostStudioHost shape', () => {
  const host = createDesktopHost();
  for (const m of ['pickPhotos', 'savePost', 'listPosts', 'getPost', 'deletePost']) {
    assert.equal(typeof host[m], 'function', `missing host.${m}`);
  }
});

// Node has no `Image`/`FileReader` (browser-only); the mobile host's
// pickPhotos/savePost run the existing downscaleDataUrl/fileToDataUrl helpers,
// so a minimal fake of each lets these tests drive real request/resolve wiring
// without a browser.
class FakeImage {
  set src(v) {
    this._src = v;
    queueMicrotask(() => {
      this.naturalWidth = 100;
      this.naturalHeight = 100;
      this.onload?.();
    });
  }
}
class FakeFileReader {
  readAsDataURL(_blob) {
    queueMicrotask(() => {
      this.result = 'data:image/png;base64,AQID';
      this.onload?.();
    });
  }
}
globalThis.Image = FakeImage;
globalThis.FileReader = FakeFileReader;

function fakeBridge() {
  return { sent: [], postMessage(json) { this.sent.push(JSON.parse(json)); } };
}
const flush = () => new Promise((r) => setTimeout(r, 0));

test('createMobileHost exposes the PostStudioHost shape', () => {
  const host = createMobileHost(fakeBridge());
  for (const m of ['pickPhotos', 'savePost', 'listPosts', 'getPost', 'deletePost']) {
    assert.equal(typeof host[m], 'function', `missing host.${m}`);
  }
});

test('listPosts sends a bridge call and resolves with the Dart reply', async () => {
  const bridge = fakeBridge();
  const host = createMobileHost(bridge);
  const p = host.listPosts();
  assert.equal(bridge.sent[0].method, 'listPosts');
  assert.equal(bridge.sent[0].args, null);
  globalThis.__psResolve(bridge.sent[0].id, JSON.stringify([{ id: 1, theme: 'dark_premium' }]));
  assert.deepEqual(await p, [{ id: 1, theme: 'dark_premium' }]);
});

test('getPost sends the id and rejects when Dart replies with an error', async () => {
  const bridge = fakeBridge();
  const host = createMobileHost(bridge);
  const p = host.getPost(7);
  assert.equal(bridge.sent[0].method, 'getPost');
  assert.deepEqual(bridge.sent[0].args, { id: 7 });
  globalThis.__psReject(bridge.sent[0].id, 'network error');
  await assert.rejects(p, /network error/);
});

test('deletePost sends the id and resolves on an empty reply', async () => {
  const bridge = fakeBridge();
  const host = createMobileHost(bridge);
  const p = host.deletePost(3);
  assert.equal(bridge.sent[0].method, 'deletePost');
  assert.deepEqual(bridge.sent[0].args, { id: 3 });
  globalThis.__psResolve(bridge.sent[0].id, null);
  await p;
});

test('pickPhotos downscales each photo Dart returns', async () => {
  const bridge = fakeBridge();
  const host = createMobileHost(bridge);
  const p = host.pickPhotos();
  assert.equal(bridge.sent[0].method, 'pickPhotos');
  globalThis.__psResolve(bridge.sent[0].id,
    JSON.stringify([{ id: 'a.jpg', dataUrl: 'data:image/jpeg;base64,AAA=' }]));
  const result = await p;
  assert.deepEqual(result, [{ id: 'a.jpg', dataUrl: 'data:image/jpeg;base64,AAA=' }]);
});

test('savePost base64-encodes the PNG and forwards templateJson + meta', async () => {
  const bridge = fakeBridge();
  const host = createMobileHost(bridge);
  const p = host.savePost({}, '{"theme":"dark_premium"}',
    { theme: 'dark_premium', size: 'square', title: 'T' });
  await flush();
  assert.equal(bridge.sent[0].method, 'savePost');
  assert.equal(bridge.sent[0].args.pngB64, 'AQID');
  assert.equal(bridge.sent[0].args.templateJson, '{"theme":"dark_premium"}');
  assert.deepEqual(bridge.sent[0].args.meta, { theme: 'dark_premium', size: 'square', title: 'T' });
  globalThis.__psResolve(bridge.sent[0].id, JSON.stringify({ id: 42 }));
  assert.deepEqual(await p, { id: 42 });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/js/host.test.mjs`
Expected: FAIL — `createMobileHost` is not exported by `../../static/post_studio/host.js`.

- [ ] **Step 3: Implement `createMobileHost` in `host.js`**

Append to `static/post_studio/host.js` (after `createDesktopHost`'s closing `}` at line 104):

```js

/**
 * @param {{postMessage: (json:string) => void}} [bridge] Injected for testing;
 * defaults to the Dart-injected `window.PostStudioBridge` JavaScriptChannel.
 * @returns {PostStudioHost}
 */
export function createMobileHost(bridge = globalThis.PostStudioBridge) {
  let seq = 0;
  const pending = new Map();

  globalThis.__psResolve = (id, resultJson) => {
    const p = pending.get(id);
    if (!p) return;
    pending.delete(id);
    p.resolve(resultJson == null ? undefined : JSON.parse(resultJson));
  };
  globalThis.__psReject = (id, message) => {
    const p = pending.get(id);
    if (!p) return;
    pending.delete(id);
    p.reject(new Error(message));
  };

  function call(method, args) {
    return new Promise((resolve, reject) => {
      const id = String(++seq);
      pending.set(id, { resolve, reject });
      bridge.postMessage(JSON.stringify({ id, method, args }));
    });
  }

  async function pickPhotos() {
    const picked = (await call('pickPhotos', null)) || [];
    const out = [];
    for (const item of picked) {
      out.push({ id: item.id, dataUrl: await downscaleDataUrl(item.dataUrl, MAX_PHOTO_DIM) });
    }
    return out;
  }

  async function savePost(png, templateJson, meta) {
    const dataUrl = await fileToDataUrl(png);
    const pngB64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
    return call('savePost', { pngB64, templateJson, meta: meta || {} });
  }

  function listPosts() {
    return call('listPosts', null).then((r) => r || []);
  }

  function getPost(id) {
    return call('getPost', { id });
  }

  function deletePost(id) {
    return call('deletePost', { id });
  }

  return { pickPhotos, savePost, listPosts, getPost, deletePost };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/js/host.test.mjs`
Expected: PASS (7 tests: 1 desktop shape + 6 mobile).

- [ ] **Step 5: Commit**

```bash
git add static/post_studio/host.js tests/js/host.test.mjs
git commit -m "feat(post-studio): add createMobileHost bridge adapter"
```

---

## Task 2: `editor.js` — `pointerProfile` option

**Files:**
- Modify: `static/post_studio/editor.js` (line 36 area for the constant, line 53 area for the derived variable, line 322 for the handle-size read)
- Modify: `static/post_studio/spike/editor_harness.html` (add a `?profile=` query-param passthrough, default unchanged)
- Test: `tests/e2e/test_editor_flow.py` (append one test)

**Interfaces:**
- Consumes: `opts.pointerProfile` passed into `mountEditor(rootEl, host, opts = {})` (editor.js:48).
- Produces: default behavior (`opts.pointerProfile` unset or `'mouse'`) stays byte-identical (handle renders at ~10 screen-px, matching the current hardcoded behavior). `opts.pointerProfile === 'touch'` renders the resize handle at ~32 screen-px. Task 4's `mobile_editor.html` passes `{pointerProfile: 'touch'}`.

- [ ] **Step 1: Write the failing test**

In `static/post_studio/spike/editor_harness.html`, change the final block (currently lines 28-31):

```html
  const profile = new URLSearchParams(location.search).get('profile') === 'touch' ? 'touch' : 'mouse';
  mountEditor(document.getElementById('root'), fakeHost, {
    initialComp: defaultComposition('before_after', { doctorName: 'DR. TEST' }),
    pointerProfile: profile,
  });
  window.__ready = true;
```

Append to `tests/e2e/test_editor_flow.py`:

```python
def test_touch_profile_grows_resize_handle():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        page = browser.new_page()
        page.goto(HARNESS.as_uri() + "?profile=touch")
        page.wait_for_function("() => window.__ready === true")
        page.wait_for_selector("[data-ps-stage]")
        page.click("[data-ps-block='0']")
        page.wait_for_selector("[data-ps-resize-handle='br']")
        size = page.eval_on_selector("[data-ps-resize-handle='br']",
            "n => { const b = n.getBoundingClientRect(); return { w: b.width, h: b.height }; }")
        # mouse profile renders ~10 screen-px, touch renders ~32 — 20 cleanly separates them
        assert size["w"] > 20 and size["h"] > 20, size
        browser.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/e2e/test_editor_flow.py::test_touch_profile_grows_resize_handle -v`
Expected: FAIL (`size["w"]` is ~10-11, not > 20) — `editor.js` doesn't read `pointerProfile` yet.

- [ ] **Step 3: Implement `pointerProfile` in `editor.js`**

In `static/post_studio/editor.js`, change line 36 from:

```js
const PREVIEW_W = 360; // displayed width; the stage renders at native export px.
```

to:

```js
const PREVIEW_W = 360; // displayed width; the stage renders at native export px.
const HANDLE_PX = { mouse: 10, touch: 32 }; // resize-handle size in screen-px, by pointerProfile
```

Change line 53 from:

```js
  const state = { comp: opts.initialComp || defaultComposition('before_after'), selectedRef: null, selectedPosRef: null };
```

to:

```js
  const state = { comp: opts.initialComp || defaultComposition('before_after'), selectedRef: null, selectedPosRef: null };
  const pointerProfile = opts.pointerProfile === 'touch' ? 'touch' : 'mouse';
```

Change line 322 from:

```js
        const hs = 10 / scale;   // handle size in native-stage px so it looks ~10 screen-px
```

to:

```js
        const hs = HANDLE_PX[pointerProfile] / scale;   // handle size in native-stage px
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/e2e/test_editor_flow.py::test_touch_profile_grows_resize_handle -v`
Expected: PASS.

Then confirm no regression on the default profile:

Run: `pytest tests/e2e/test_editor_flow.py -v`
Expected: all 17 tests PASS (16 existing + 1 new).

- [ ] **Step 5: Commit**

```bash
git add static/post_studio/editor.js static/post_studio/spike/editor_harness.html tests/e2e/test_editor_flow.py
git commit -m "feat(post-studio): add pointerProfile option for touch hit-targets"
```

---

## Task 3: Dart `PostStudioBridgeHandler`

**Files:**
- Create: `clinic_mobile_app/lib/services/post_studio_bridge_handler.dart`
- Test: `clinic_mobile_app/test/post_studio_bridge_handler_test.dart`

**Interfaces:**
- Consumes: `ClinicApi` (`clinic_mobile_app/lib/services/clinic_api.dart`) — `get`, `getList`, `delete`, `postMultipart` (all non-`final`, overridable in test fakes); `image_picker`'s `ImagePicker().pickMultiImage()` / `XFile`; `path_provider`'s `getTemporaryDirectory()`.
- Produces: `PostStudioBridgeHandler({required ClinicApi api, required Future<void> Function(String) runJavaScript, Future<List<XFile>> Function()? pickImages, Future<String> Function(Uint8List)? writeTempPng})` with `Future<void> onMessage(String raw)`. Task 4's `PostStudioScreen` constructs one per screen instance, wiring `runJavaScript: controller.runJavaScript` and registering `handler.onMessage` as the `PostStudioBridge` JavaScriptChannel's `onMessageReceived`.

- [ ] **Step 1: Write the failing tests**

Create `clinic_mobile_app/test/post_studio_bridge_handler_test.dart`:

```dart
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `flutter test test/post_studio_bridge_handler_test.dart`
Expected: FAIL — `package:clinic_mobile_app/services/post_studio_bridge_handler.dart` does not exist.

- [ ] **Step 3: Implement `PostStudioBridgeHandler`**

Create `clinic_mobile_app/lib/services/post_studio_bridge_handler.dart`:

```dart
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
    } on Exception catch (e) {
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `flutter test test/post_studio_bridge_handler_test.dart`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add clinic_mobile_app/lib/services/post_studio_bridge_handler.dart clinic_mobile_app/test/post_studio_bridge_handler_test.dart
git commit -m "feat(post-studio): add PostStudioBridgeHandler for the mobile JS<->Dart bridge"
```

---

## Task 4: `PostStudioScreen` + assets + wiring

**Files:**
- Modify: `clinic_mobile_app/pubspec.yaml` (dependencies block ends line 59; assets block is lines 99-100)
- Create: `tools/sync_post_studio_mobile_assets.py`
- Create: `clinic_mobile_app/assets/post_studio/mobile_editor.html`
- Create: `clinic_mobile_app/lib/screens/post_studio_screen.dart`
- Modify: `clinic_mobile_app/lib/screens/home_screen.dart` (import line 14, list entry line 34)

**Interfaces:**
- Consumes: `PostStudioBridgeHandler` (Task 3); `AppState.api` (`clinic_mobile_app/lib/state/app_state.dart:30`, typed `ClinicApi`); `AppState.isArabic`; `AppStrings.t('failed_to_load_data', isArabic: ...)` (existing key, `clinic_mobile_app/lib/utils/app_strings.dart`).
- Produces: `PostStudioScreen` widget, wired into `home_screen.dart`'s screen list in place of `PostsScreen`.

- [ ] **Step 1: Add the `webview_flutter` dependency and the assets folder**

In `clinic_mobile_app/pubspec.yaml`, change line 59 from:

```yaml
  share_plus: ^11.0.0
```

to:

```yaml
  share_plus: ^11.0.0
  webview_flutter: ^4.14.0
```

Change lines 99-100 from:

```yaml
  assets:
    - assets/icon/dentacare_icon.png
```

to:

```yaml
  assets:
    - assets/icon/dentacare_icon.png
    - assets/post_studio/
```

- [ ] **Step 2: Fetch the new dependency**

Run: `cd clinic_mobile_app && flutter pub get`
Expected: exits 0, `webview_flutter` resolved (`4.14.0` or a compatible newer patch).

- [ ] **Step 3: Create the asset-sync script**

Create `tools/sync_post_studio_mobile_assets.py`:

```python
"""Mirror static/post_studio/*.js into clinic_mobile_app/assets/post_studio/ for
the Flutter asset bundler (P6 mobile parity). static/post_studio/ stays the
single source of truth for the JS modules; mobile_editor.html is hand-written
and lives only under the Flutter assets folder. Run after editing any
static/post_studio/*.js file, before an APK/IPA build:
    python tools/sync_post_studio_mobile_assets.py
"""
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "static" / "post_studio"
DEST = ROOT / "clinic_mobile_app" / "assets" / "post_studio"

JS_MODULES = [
    "composition.js", "themes.js", "render.js", "rasterize.js",
    "fonts.js", "inspector.js", "editor.js", "host.js",
]


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for name in JS_MODULES:
        shutil.copyfile(SRC / name, DEST / name)
    print(f"synced {len(JS_MODULES)} modules to {DEST}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the sync script**

Run: `python tools/sync_post_studio_mobile_assets.py`
Expected: `synced 8 modules to .../clinic_mobile_app/assets/post_studio` — verify with `ls clinic_mobile_app/assets/post_studio/` (8 `.js` files present).

- [ ] **Step 5: Create the mobile shell HTML**

Create `clinic_mobile_app/assets/post_studio/mobile_editor.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
  <title>Post Studio</title>
</head>
<body>
<div id="root"></div>
<script type="module">
  import { mountEditor } from './editor.js';
  import { createMobileHost } from './host.js';
  mountEditor(document.getElementById('root'), createMobileHost(), { pointerProfile: 'touch' });
  window.__ready = true;
</script>
</body>
</html>
```

- [ ] **Step 6: Create `PostStudioScreen`**

Create `clinic_mobile_app/lib/screens/post_studio_screen.dart`:

```dart
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../services/post_studio_bridge_handler.dart';
import '../state/app_state.dart';
import '../utils/app_strings.dart';

/// Full editor parity with desktop's Post Studio: mounts the same client-side
/// WYSIWYG editor bundle (static/post_studio/, synced into
/// assets/post_studio/) inside a WebView, bridged to ClinicApi via
/// [PostStudioBridgeHandler]. Replaces the old read-only PostsScreen.
class PostStudioScreen extends StatefulWidget {
  const PostStudioScreen({super.key});

  @override
  State<PostStudioScreen> createState() => _PostStudioScreenState();
}

class _PostStudioScreenState extends State<PostStudioScreen> {
  late final WebViewController _controller;
  bool _loadFailed = false;
  bool _initialized = false;
  String? _trustedOrigin;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_initialized) return;
    _initialized = true;
    final handler = PostStudioBridgeHandler(
      api: context.read<AppState>().api,
      runJavaScript: (script) => _controller.runJavaScript(script),
    );
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onNavigationRequest: _onNavigationRequest,
        onWebResourceError: (_) {
          if (mounted) setState(() => _loadFailed = true);
        },
      ))
      ..addJavaScriptChannel(
        'PostStudioBridge',
        onMessageReceived: (message) => unawaited(handler.onMessage(message.message)),
      )
      ..loadFlutterAsset('assets/post_studio/mobile_editor.html');
  }

  // Never load arbitrary URLs — only navigations within the bundled asset's
  // own origin (established on first load) are allowed.
  NavigationDecision _onNavigationRequest(NavigationRequest request) {
    final uri = Uri.tryParse(request.url);
    if (uri == null) return NavigationDecision.prevent;
    final origin = '${uri.scheme}://${uri.authority}';
    _trustedOrigin ??= origin;
    return origin == _trustedOrigin ? NavigationDecision.navigate : NavigationDecision.prevent;
  }

  @override
  Widget build(BuildContext context) {
    final ar = context.watch<AppState>().isArabic;
    if (_loadFailed) {
      return Scaffold(
        body: Center(child: Text(AppStrings.t('failed_to_load_data', isArabic: ar))),
      );
    }
    return Scaffold(body: WebViewWidget(controller: _controller));
  }
}
```

- [ ] **Step 7: Wire it into `home_screen.dart`**

In `clinic_mobile_app/lib/screens/home_screen.dart`, change line 14 from:

```dart
import 'posts_screen.dart';
```

to:

```dart
import 'post_studio_screen.dart';
```

Change line 34 from:

```dart
    const PostsScreen(),
```

to:

```dart
    const PostStudioScreen(),
```

- [ ] **Step 8: Verify**

Run: `cd clinic_mobile_app && flutter analyze`
Expected: clean. `posts_screen.dart`/`post_service.dart`/`marketing_post.dart` still exist on disk but are now unreferenced — dead, not broken; Task 5 deletes them outright.

Run: `cd clinic_mobile_app && flutter test`
Expected: full suite green, including Task 3's 9 new bridge-handler tests.

- [ ] **Step 9: Commit**

```bash
git add clinic_mobile_app/pubspec.yaml clinic_mobile_app/pubspec.lock tools/sync_post_studio_mobile_assets.py clinic_mobile_app/assets/post_studio/ clinic_mobile_app/lib/screens/post_studio_screen.dart clinic_mobile_app/lib/screens/home_screen.dart
git commit -m "feat(post-studio): mount the WYSIWYG editor bundle in a mobile WebView"
```

---

## Task 5: Retire the old read-only gallery

**Files:**
- Delete: `clinic_mobile_app/lib/screens/posts_screen.dart`
- Delete: `clinic_mobile_app/lib/services/post_service.dart`
- Delete: `clinic_mobile_app/lib/models/marketing_post.dart`
- Delete: `clinic_mobile_app/test/marketing_post_test.dart`

**Interfaces:**
- Consumes: nothing (verified via `grep -rn "MarketingPost\|PostService\|posts_screen" clinic_mobile_app/lib` — only these 4 files plus `home_screen.dart`'s already-updated wiring reference these symbols; no other file needs them).
- Produces: nothing new — pure deletion.

- [ ] **Step 1: Delete the four files**

```bash
git rm clinic_mobile_app/lib/screens/posts_screen.dart clinic_mobile_app/lib/services/post_service.dart clinic_mobile_app/lib/models/marketing_post.dart clinic_mobile_app/test/marketing_post_test.dart
```

- [ ] **Step 2: Verify no dangling references**

Run: `cd clinic_mobile_app && flutter analyze`
Expected: clean — no `unused_import` / `undefined_class` errors referencing the deleted files.

- [ ] **Step 3: Verify the full suite still passes**

Run: `cd clinic_mobile_app && flutter test`
Expected: full suite green (4 fewer test cases from the deleted `marketing_post_test.dart`; everything else unaffected).

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor(post-studio): remove the retired read-only posts gallery"
```

---

## Task 6: Final cross-stack verification gate

**Files:** none (verification only).

**Interfaces:** none — this task confirms every prior task's changes compose cleanly across the JS, Python/Playwright, and Dart/Flutter test suites.

- [ ] **Step 1: Full JS unit suite**

Run: `node --test tests/js/`
Expected: all pass (composition, themes, fonts, host — host.js now includes the 6 new mobile tests from Task 1).

- [ ] **Step 2: Syntax-check the touched JS modules**

Run: `node --check static/post_studio/host.js && node --check static/post_studio/editor.js`
Expected: no output, exit 0.

- [ ] **Step 3: Full desktop Playwright suite**

Run: `pytest tests/e2e/test_editor_flow.py tests/e2e/test_post_studio_smoke.py -v`
Expected: all pass (17 tests in `test_editor_flow.py` including Task 2's new touch-profile test, plus the smoke suite).

- [ ] **Step 4: Full Python suite (regression check — P6 touches no Python)**

Run: `python -m pytest tests/`
Expected: exit 0, no regressions.

- [ ] **Step 5: Dart analyze + full Flutter suite**

Run: `cd clinic_mobile_app && dart analyze`
Expected: clean.

Run: `cd clinic_mobile_app && flutter test`
Expected: full suite green.

- [ ] **Step 6: Record the outcome**

If every command above is green, P6 is code-complete. No commit needed for this task unless a fix was required during the gate (in which case, fix, re-run the affected command, and commit the fix with a normal `fix(post-studio): ...` message).

**Known, accepted gap (per the approved spec, not fixed by this plan):** WebView mount, real touch-drag/resize, and the bundled asset actually loading on a device are not covered by automated tests in this environment — real-device/emulator smoke is required before calling P6 done from the user's side. The whole `feat/post-studio` branch's PR stays HELD per the Global Constraints.
