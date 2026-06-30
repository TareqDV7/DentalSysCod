import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FONT_FACE_CSS, FONT_OPTIONS, ensureFontsLoaded }
  from '../../static/post_studio/fonts.js';

test('FONT_FACE_CSS bundles all four families as base64 data URLs', () => {
  for (const fam of ['Manrope', 'Playfair Display', 'Cairo', 'Poppins']) {
    assert.ok(FONT_FACE_CSS.includes(`font-family:'${fam}'`), `missing ${fam}`);
  }
  assert.ok(FONT_FACE_CSS.includes('url(data:font/ttf;base64,'), 'fonts not inlined');
  assert.ok(FONT_FACE_CSS.includes('font-weight:800'), 'Manrope ExtraBold missing');
  assert.ok(FONT_FACE_CSS.includes("font-family:'Poppins';font-style:normal;font-weight:700"),
    'Poppins Bold missing');
});

test('FONT_OPTIONS exposes the curated families with required keys', () => {
  assert.ok(FONT_OPTIONS.length >= 3);
  const ids = FONT_OPTIONS.map((o) => o.id);
  assert.deepEqual(ids, ['manrope', 'playfair', 'cairo', 'poppins']);
  for (const o of FONT_OPTIONS) {
    for (const k of ['id', 'label', 'label_ar', 'family']) {
      assert.ok(o[k], `option ${o.id} missing ${k}`);
    }
  }
});

test('ensureFontsLoaded is DOM-only (callable with a fake doc, idempotent)', () => {
  let appended = 0;
  const fakeStyle = {};
  const fakeDoc = {
    _byId: {},
    getElementById(id) { return this._byId[id] || null; },
    createElement() { return fakeStyle; },
    head: { appendChild(node) { appended += 1; fakeDoc._byId['ps-font-faces'] = node; } },
  };
  ensureFontsLoaded(fakeDoc);
  ensureFontsLoaded(fakeDoc);     // second call must no-op
  assert.equal(appended, 1, 'must inject the <style> exactly once');
  assert.equal(fakeStyle.id, 'ps-font-faces');
  assert.equal(fakeStyle.textContent, FONT_FACE_CSS);
});
