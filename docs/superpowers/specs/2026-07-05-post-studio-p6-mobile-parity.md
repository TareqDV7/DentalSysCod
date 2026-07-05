# Post Studio — P6: Mobile Editor Parity (Design Spec)

**Date:** 2026-07-05
**Branch:** `feat/post-studio`
**Phase:** P6 (final phase — last thing before the PR)
**Status:** Approved design — ready for implementation plan.

## Context

Desktop's Post Studio is now a full client-side WYSIWYG editor (P2–P5):
pure-ESM modules under `static/post_studio/` (`composition.js`, `themes.js`,
`render.js`, `rasterize.js`, `fonts.js`, `inspector.js`, `editor.js`, `host.js`)
mounted in the desktop WebView via `createDesktopHost()`. The original master
spec assumed mobile parity would need "save → local DB → existing sync," but
the mobile app's *current* Post Studio integration (`posts_screen.dart` +
`post_service.dart`) is already a **native, read-only, network-direct**
gallery: it calls `GET /api/posts` / `GET /api/posts/<id>/image` straight
through the existing authed `ClinicApi` (device-token header, LAN/cloud
`baseUrl` resolution) — no local SQLite mirror, no sync integration, same
pattern as `medical_image_service.dart`. Desktop's `host.js savePost()`
likewise posts a multipart form (`image` PNG + `template_json` + theme/size/
title) straight to `POST /api/posts`. `ClinicApi` already has `postMultipart`.
So mobile creation can follow the exact same network-direct pattern as mobile
reading already does — no new backend endpoint, no local-DB/sync work.

`clinic_mobile_app/pubspec.yaml` does not yet depend on `webview_flutter`;
`image_picker` is already present (matches the original master decision).

## Goal

Mount the same editor bundle inside a Flutter `webview_flutter` WebView,
replacing the native read-only gallery entirely, with a Dart-side host
adapter that reuses the existing `ClinicApi`/`image_picker` — so mobile gets
full create/edit parity with desktop, not just viewing.

## Decisions (all user-approved 2026-07-05)

1. **Replace `PostsScreen` entirely.** The editor bundle already renders its
   own gallery (list/reopen/delete) alongside the canvas — one WebView screen
   does both, matching desktop exactly. `posts_screen.dart`,
   `post_service.dart`, `models/marketing_post.dart`, and
   `test/marketing_post_test.dart` are deleted outright (confirmed via grep:
   no other file in `clinic_mobile_app` references any of them except
   `home_screen.dart`'s single wiring point).
2. **Single JS↔Dart bridge, JSON-RPC style.** One `JavaScriptChannel`
   (`PostStudioBridge`) carries `{id, method, args}` messages; Dart routes by
   `method` and replies by injecting `window.__psResolve(id, result)` /
   `window.__psReject(id, error)`. One channel, one Dart-side `switch`, mirrors
   `host.js`'s existing method shape almost 1:1 — cheaper than 5 separate
   channels, and keeps the `PostStudioHost` interface (`pickPhotos`,
   `savePost`, `listPosts`, `getPost`, `deletePost`) as the single contract
   both hosts implement.
3. **Dart owns auth/network; JS owns image processing.** `pickPhotos`'s Dart
   side only uses `image_picker` to select files, reads bytes, base64-encodes,
   and replies with raw data URLs — the **existing** `downscaleDataUrl()` /
   `MAX_PHOTO_DIM` (already shipped in `host.js`, reused verbatim, not
   reimplemented in Dart) still does the canvas-based resize on the JS side.
   `savePost`'s Dart side decodes the base64 PNG the JS side already
   rasterized, writes it to a temp file (`path_provider`), and calls the
   **existing** `ClinicApi.postMultipart()` against `/api/posts` — the exact
   endpoint desktop already hits. No new backend route.
4. **Touch hit targets via an explicit `pointerProfile` option.**
   `mountEditor(root, host, {pointerProfile: 'touch'|'mouse'})`. Resize
   handles and drag hit-testing grow their tap radius under `'touch'` (~32px)
   without changing their visual size or desktop's already-shipped/reviewed
   behavior under `'mouse'` (the default, unchanged at 10px). Pointer Events
   (already used throughout `editor.js` for drag/resize) fire uniformly for
   mouse/touch/pen, so this is the only touch-specific change needed —
   keyboard nudge (arrow keys) simply goes unused on mobile, no harm.
5. **Bundled assets, not cross-directory Flutter asset paths.**
   `static/post_studio/` (desktop's live files) stays the single source of
   truth. A small sync step mirrors the JS modules into
   `clinic_mobile_app/assets/post_studio/` for Flutter's asset bundler —
   same precedent as `tools/gen_post_studio_fonts.py` generating `fonts.js`.
   Editing `editor.js` means re-running the sync before an APK build
   (documented in the plan, not auto-hooked — matches how font regen already
   works today).
6. **WebView testing gap is a known, accepted device-smoke item.**
   `webview_flutter` cannot be meaningfully driven headless in `flutter_test`
   in this environment (no real device/emulator). Automated coverage stops at
   the bridge handler's Dart-side logic (unit-tested with fakes) and the JS
   modules (`node --test`); actual WebView mount + touch-drag verification is
   a real-device smoke item — consistent with every prior mobile-parity phase
   in this project.

## Architecture

### Bridge protocol

```
JS  → channel.postMessage(JSON.stringify({id, method, args}))
Dart → controller.runJavaScript("window.__psResolve(<id>, <jsonResult>)")
     → controller.runJavaScript("window.__psReject(<id>, <jsonError>)")
```

JS side keeps a `Map<id, {resolve, reject}>` of in-flight calls (new file-local
state inside `createMobileHost()`), resolved/rejected when Dart's injected
call runs. `id` is a simple incrementing counter, scoped to the host instance.

### JS: `static/post_studio/host.js` — new `createMobileHost()`

Sibling factory to `createDesktopHost()`, same `PostStudioHost` return shape:

- `pickPhotos()` → bridge-call `'pickPhotos'` (no args) → Dart replies with
  `[{id, dataUrl}]` (already base64 data URLs) → each run through the
  **existing, unchanged** `downscaleDataUrl(dataUrl, MAX_PHOTO_DIM)`.
- `savePost(png, templateJson, meta)` → converts the PNG `Blob` to a base64
  string (via `FileReader`, mirrors the existing `fileToDataUrl` helper) →
  bridge-call `'savePost'` with `{pngB64, templateJson, meta}` → Dart returns
  `{id}` or throws.
- `listPosts()` / `getPost(id)` / `deletePost(id)` → thin bridge-call
  passthroughs, same return shapes as desktop's fetch-based versions.

### Dart: new `PostStudioBridgeHandler` (`lib/services/`)

Registered as the `WebViewController`'s `onMessageReceived` handler for the
`PostStudioBridge` channel. Routes by `method`:

| method | implementation |
|---|---|
| `pickPhotos` | `image_picker` multi-select → read bytes → base64 → reply array |
| `savePost` | decode base64 PNG → write temp file (`path_provider`) → `ClinicApi.postMultipart('/api/posts', ...)` (same fields desktop's `savePost` sends: `image`, `template_json`, `theme`, `size`, `title`) |
| `listPosts` | `ClinicApi.get('/api/posts')` |
| `getPost` | `ClinicApi.get('/api/posts/$id')` |
| `deletePost` | `ClinicApi.delete('/api/posts/$id')` |

Constructed with the same `context.read<AppState>().api` the old
`PostsScreen` already used — no new auth/discovery logic.

### Dart: new `PostStudioScreen` (`lib/screens/`)

Replaces `PostsScreen` at `home_screen.dart:34`. Builds a `WebViewController`,
sets `JavaScriptMode.unrestricted` (JS required — this is the whole editor),
registers the `PostStudioBridge` `JavaScriptChannel` wired to
`PostStudioBridgeHandler`, sets a `NavigationDelegate` restricting navigation
to the bundled asset origin only (security: never load arbitrary URLs), loads
`assets/post_studio/mobile_editor.html` via `loadFlutterAsset`.

### `clinic_mobile_app/assets/post_studio/mobile_editor.html` (new)

Production shell, mirrors `static/post_studio/spike/editor_harness.html`'s
structure but mounts the real bridge host instead of a fake in-memory one:

```html
<script type="module">
  import { mountEditor } from './editor.js';
  import { createMobileHost } from './host.js';
  mountEditor(document.getElementById('root'), createMobileHost(),
    { pointerProfile: 'touch' });
</script>
```

### `static/post_studio/editor.js` — `pointerProfile` option

`mountEditor(rootEl, host, opts = {})` gains `opts.pointerProfile` (default
`'mouse'`). Resize-handle size and drag hit-testing radius read from a small
lookup (`{mouse: 10, touch: 32}` native-px) instead of the current hardcoded
`10`. Desktop's call site is unchanged (defaults to `'mouse'`, byte-identical
behavior); only the mobile shell passes `'touch'`.

### Retirement

Deleted outright: `lib/screens/posts_screen.dart`,
`lib/services/post_service.dart`, `lib/models/marketing_post.dart`,
`test/marketing_post_test.dart`.

### Files

- `static/post_studio/host.js` — `createMobileHost()` (new, shared source)
- `static/post_studio/editor.js` — `pointerProfile` opt, handle-size lookup
- `clinic_mobile_app/pubspec.yaml` — add `webview_flutter`, declare
  `assets/post_studio/` asset folder
- `clinic_mobile_app/assets/post_studio/*` — synced copies of the JS modules
  + new `mobile_editor.html`
- `clinic_mobile_app/lib/services/post_studio_bridge_handler.dart` — new
- `clinic_mobile_app/lib/screens/post_studio_screen.dart` — new
- `clinic_mobile_app/lib/screens/home_screen.dart` — swap screen reference
- deletions listed above

## Data flow

1. `PostStudioScreen` mounts → WebView loads `mobile_editor.html` →
   `mountEditor` runs with `createMobileHost()` + `pointerProfile:'touch'`.
2. Editor's built-in gallery calls `host.listPosts()` on mount (existing
   editor.js behavior, unchanged) → bridge round-trip → `ClinicApi.get`.
3. User adds photos → `host.pickPhotos()` → `image_picker` → Dart base64
   reply → JS downscales → composition state updated (existing editor.js
   logic, unchanged).
4. User drags/resizes/edits (existing editor.js logic, unchanged — Pointer
   Events already abstract touch).
5. Save → existing `rasterize.js` export → `host.savePost(png, json, meta)` →
   bridge → Dart temp-file write → `ClinicApi.postMultipart` → `/api/posts`.

## Error handling

- Bridge rejections propagate as JS `Promise` rejections through the same
  `PostStudioHost` contract desktop already uses — editor.js's existing
  try/catch+toast wiring (shipped in P2b) needs **no changes** to surface
  them.
- `image_picker` cancel → Dart replies with an empty array (not a rejection)
  — "no photos picked" is a no-op, not an error.
- `NavigationDelegate.onWebResourceError` → simple bilingual inline message
  if the bundled shell itself fails to load (should not happen in practice —
  it's a local asset, not a network fetch — but the delegate is there for
  defense-in-depth per the WebView security rules).
- `NavigationDelegate.onNavigationRequest` rejects any navigation away from
  the bundled asset origin (no arbitrary URL loading).

## Testing (TDD)

- **`host.test.mjs` (node --test):** `createMobileHost()`'s each method
  against a fake bridge object (mock `postMessage` capturing the sent
  `{method,args}`, manually resolving/rejecting to drive the returned
  Promise) — covers request shape and resolve/reject propagation without a
  real WebView.
- **`editor.js` touch-profile:** extend existing render/e2e coverage —
  handle size differs under `pointerProfile:'touch'` vs default `'mouse'`;
  desktop's existing e2e suite (34 tests) stays green unchanged (default
  profile is byte-identical to today).
- **Dart unit tests (`test/post_studio_bridge_handler_test.dart`):** each
  bridge method against a fake `ClinicApi` and a fake `image_picker` —
  `pickPhotos` returns base64 data for selected files / empty on cancel;
  `savePost` writes a temp file and calls `postMultipart` with the right
  fields; `listPosts`/`getPost`/`deletePost` passthrough correctly; network
  failure surfaces as a bridge rejection.
- `dart analyze` clean; `flutter test` full suite green.
- **Explicit known gap:** WebView mount, real touch-drag/resize, and the
  bundled asset actually loading on a device are **not** covered by automated
  tests in this environment — real-device/emulator smoke is required before
  calling P6 done from the user's side (same as every prior mobile-parity
  phase).

## Non-goals (YAGNI — deferred)

- No local SQLite mirror or background sync for posts — matches how mobile
  Post Studio already behaves today (network-direct, same as medical images).
- No new backend endpoints — `/api/posts` and friends are unchanged.
- No offline authoring — creating/editing a post requires being connected to
  the paired local/cloud server, same requirement the read-only gallery
  already had.
- No non-square (portrait/story) canvas support on mobile beyond whatever
  desktop already has (still unreachable via any UI, per the P4b carried-minor
  note — out of scope here too).
- No automated on-device UI test harness — real-device smoke stays a manual
  user-side step, not built out as CI infrastructure this phase.
- **PR remains HELD.** P6 is the last phase — once it lands, the whole
  `feat/post-studio` branch (Pillow retirement + full WYSIWYG editor +
  mobile parity) becomes the single PR. Do not open a PR or push to origin
  unprompted.
