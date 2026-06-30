import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MAX_BLOCKS, SIZES, TEMPLATES,
  defaultComposition, serialize, deserialize,
} from '../../static/post_studio/composition.js';

test('constants', () => {
  assert.equal(MAX_BLOCKS, 6);
  assert.deepEqual(SIZES, ['square', 'portrait', 'story']);
  assert.ok(TEMPLATES.includes('before_after'));
});

test('defaultComposition(before_after) has title + 2-block strip + doctor', () => {
  const c = defaultComposition('before_after', { doctorName: 'DR. WASFY BARZAQ' });
  assert.equal(c.version, 1);
  assert.ok(SIZES.includes(c.size));
  const ids = c.elements.map((e) => e.id);
  assert.deepEqual(ids, ['title', 'strip', 'doctor']);
  const strip = c.elements.find((e) => e.id === 'strip');
  assert.equal(strip.blocks.length, 2);
  assert.deepEqual(strip.blocks.map((b) => b.badge), [1, 2]);
  const doctor = c.elements.find((e) => e.id === 'doctor');
  assert.equal(doctor.text, 'DR. WASFY BARZAQ');
});

test('defaultComposition is immutable across calls (no shared refs)', () => {
  const a = defaultComposition('before_after');
  const b = defaultComposition('before_after');
  a.elements.find((e) => e.id === 'strip').blocks.push({ photo: null, badge: 9, label: 'x' });
  const bStrip = b.elements.find((e) => e.id === 'strip');
  assert.equal(bStrip.blocks.length, 2, 'second composition must not share block arrays');
});

test('unknown template throws', () => {
  assert.throws(() => defaultComposition('nope'), /unknown template/i);
});

test('serialize/deserialize round-trips losslessly', () => {
  const c = defaultComposition('multi_phase', { doctorName: 'DR. X' });
  const back = deserialize(serialize(c));
  assert.deepEqual(back, c);
});

test('deserialize rejects wrong version and bad size', () => {
  assert.throws(() => deserialize(JSON.stringify({ version: 2, size: 'square', theme: 't', elements: [] })), /version/i);
  assert.throws(() => deserialize(JSON.stringify({ version: 1, size: 'wat', theme: 't', elements: [] })), /size/i);
});

import { addBlock, removeBlock, reorderBlock, insertBlock } from '../../static/post_studio/composition.js';

function strip(c) { return c.elements.find((e) => e.id === 'strip'); }

test('addBlock appends and renumbers', () => {
  const c = addBlock(defaultComposition('before_after'), 'Follow-up');
  assert.deepEqual(strip(c).blocks.map((b) => b.badge), [1, 2, 3]);
  assert.equal(strip(c).blocks[2].label, 'Follow-up');
});

test('addBlock enforces the 6-block cap', () => {
  let c = defaultComposition('quad_grid'); // 4 blocks
  c = addBlock(c); c = addBlock(c);          // 6
  assert.equal(strip(c).blocks.length, MAX_BLOCKS);
  assert.throws(() => addBlock(c), /max|cap|6/i);
});

test('removeBlock drops one and renumbers', () => {
  const c = removeBlock(defaultComposition('multi_phase'), 1); // drop 'During'
  assert.deepEqual(strip(c).blocks.map((b) => b.label), ['Before', 'After']);
  assert.deepEqual(strip(c).blocks.map((b) => b.badge), [1, 2]);
});

test('reorderBlock moves and renumbers', () => {
  const c = reorderBlock(defaultComposition('multi_phase'), 2, 0); // After -> front
  assert.deepEqual(strip(c).blocks.map((b) => b.label), ['After', 'Before', 'During']);
  assert.deepEqual(strip(c).blocks.map((b) => b.badge), [1, 2, 3]);
});

test('insertBlock inserts between and renumbers', () => {
  const c = insertBlock(defaultComposition('before_after'), 1, 'Mid');
  assert.deepEqual(strip(c).blocks.map((b) => b.label), ['Before Treatment', 'Mid', 'After Treatment']);
  assert.deepEqual(strip(c).blocks.map((b) => b.badge), [1, 2, 3]);
});

test('mutators do not mutate their input', () => {
  const base = defaultComposition('before_after');
  addBlock(base, 'x');
  assert.equal(strip(base).blocks.length, 2);
});

import { applyTheme } from '../../static/post_studio/composition.js';

test('applyTheme stamps per-element typography from the theme, preserves content', () => {
  const c0 = defaultComposition('before_after', { doctorName: 'DR. X' });
  const c = applyTheme(c0, 'light_luxury');
  assert.equal(c.theme, 'light_luxury');
  const title = c.elements.find((e) => e.id === 'title');
  assert.equal(title.headline.font, 'Playfair Display');   // serif headline
  assert.equal(title.headline.text, 'Procedure Title');    // content preserved
  const doctor = c.elements.find((e) => e.id === 'doctor');
  assert.equal(doctor.text, 'DR. X');                      // content preserved
  assert.equal(doctor.color, '#b08d3c');                  // restyled by theme
});

test('defaultComposition applies dark_premium (Navy & Gold) by default: Poppins headline', () => {
  const c = defaultComposition('before_after');
  assert.equal(c.theme, 'dark_premium');
  const title = c.elements.find((e) => e.id === 'title');
  assert.equal(title.headline.font, 'Poppins');
  assert.equal(title.headline.color, '#F5F5F0');
});

test('applyTheme preserves strip blocks (photos/badges/labels)', () => {
  let c = addBlock(defaultComposition('before_after'), 'Follow-up'); // 3 blocks
  c = applyTheme(c, 'clinical_premium');
  const s = c.elements.find((e) => e.id === 'strip');
  assert.deepEqual(s.blocks.map((b) => b.badge), [1, 2, 3]);
  assert.deepEqual(s.blocks.map((b) => b.label), ['Before Treatment', 'After Treatment', 'Follow-up']);
});

test('applyTheme does not mutate its input', () => {
  const c0 = defaultComposition('before_after');
  const before = JSON.stringify(c0);
  applyTheme(c0, 'bold_editorial');
  assert.equal(JSON.stringify(c0), before);
});
