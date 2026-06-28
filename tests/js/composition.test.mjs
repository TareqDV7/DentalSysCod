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
