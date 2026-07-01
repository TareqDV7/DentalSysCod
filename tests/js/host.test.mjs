import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createDesktopHost } from '../../static/post_studio/host.js';

test('createDesktopHost exposes the PostStudioHost shape', () => {
  const host = createDesktopHost();
  for (const m of ['pickPhotos', 'savePost', 'listPosts', 'getPost', 'deletePost']) {
    assert.equal(typeof host[m], 'function', `missing host.${m}`);
  }
});
