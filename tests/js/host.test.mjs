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
