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

import {
  setText, setTypography, setBlockLabel, setBlockPhoto, SIZE_MIN, SIZE_MAX,
} from '../../static/post_studio/composition.js';

function comp() { return defaultComposition('before_after'); }

test('setText sets the run text immutably', () => {
  const c0 = comp();
  const c1 = setText(c0, 'title.headline', 'Whitening');
  const t0 = c0.elements.find((e) => e.id === 'title');
  const t1 = c1.elements.find((e) => e.id === 'title');
  assert.equal(t1.headline.text, 'Whitening');
  assert.notEqual(t0.headline.text, 'Whitening');   // input not mutated
});

test('setText supports subline and doctor, rejects bad refs', () => {
  const c = comp();
  assert.equal(setText(c, 'title.subline', 'Sub').elements.find((e) => e.id === 'title').subline.text, 'Sub');
  assert.equal(setText(c, 'doctor', 'DR. X').elements.find((e) => e.id === 'doctor').text, 'DR. X');
  assert.throws(() => setText(c, 'strip.label', 'no'));
});

test('setTypography merges font/weight, clamps size, validates hex', () => {
  const c = comp();
  const out = setTypography(c, 'title.headline',
    { font: 'Cairo', weight: 800, size: 999, color: '#abcdef' });
  const h = out.elements.find((e) => e.id === 'title').headline;
  assert.equal(h.font, 'Cairo');
  assert.equal(h.weight, 800);
  assert.equal(h.size, SIZE_MAX);                 // 999 clamped to 160
  assert.equal(h.color, '#abcdef');
  // below-min clamps up; invalid hex ignored (keeps prior color)
  const out2 = setTypography(out, 'title.headline', { size: 2, color: 'red' });
  const h2 = out2.elements.find((e) => e.id === 'title').headline;
  assert.equal(h2.size, SIZE_MIN);
  assert.equal(h2.color, '#abcdef');
});

test('setTypography on strip.label writes the shared labelStyle', () => {
  const c = comp();
  const out = setTypography(c, 'strip.label', { size: 44 });
  assert.equal(out.elements.find((e) => e.id === 'strip').labelStyle.size, 44);
});

test('setBlockLabel and setBlockPhoto are immutable per-block updates', () => {
  const c = comp();
  const c1 = setBlockLabel(c, 0, 'Day 1');
  assert.equal(c1.elements.find((e) => e.id === 'strip').blocks[0].label, 'Day 1');
  assert.equal(c.elements.find((e) => e.id === 'strip').blocks[0].label, 'Before Treatment');
  const c2 = setBlockPhoto(c, 1, 'data:image/png;base64,AAAA');
  assert.equal(c2.elements.find((e) => e.id === 'strip').blocks[1].photo, 'data:image/png;base64,AAAA');
  assert.equal(c.elements.find((e) => e.id === 'strip').blocks[1].photo, null);
});

import {
  seedLayout, ensureLayout, hasLayout, CANVAS_DIMS,
} from '../../static/post_studio/composition.js';

test('defaultComposition seeds positions for every element', () => {
  const c = defaultComposition('before_after');   // dark_premium default
  const title = c.elements.find((e) => e.id === 'title');
  const strip = c.elements.find((e) => e.id === 'strip');
  const doctor = c.elements.find((e) => e.id === 'doctor');
  assert.ok(title.pos && strip.blocks[0].panelPos && strip.blocks[0].pillPos && doctor.pos);
  assert.equal(hasLayout(c), true);
});

test('dark_premium seeds the exact go.png grid', () => {
  // 4-panel dark_premium comp (quad_grid) -> the go.png panel row + pills
  const c = defaultComposition('quad_grid');
  const strip = c.elements.find((e) => e.id === 'strip');
  const doctor = c.elements.find((e) => e.id === 'doctor');
  assert.equal(strip.panelW, 250 / 1080);
  assert.equal(strip.panelH, 320 / 1080);
  assert.equal(strip.blocks[0].panelPos.y, 360 / 1080);
  assert.equal(strip.blocks[0].panelPos.x, 16 / 1080);           // centered row: 4*250+3*16=1048 -> start 16
  assert.equal(strip.blocks[1].panelPos.x, (16 + 266) / 1080);   // panelW+gap = 266
  assert.equal(strip.blocks[0].pillPos.y, 708 / 1080);
  assert.equal(doctor.pos.y, 920 / 1080);
});

test('a generic theme derives a centered, row-filling layout', () => {
  const c = applyTheme(defaultComposition('before_after'), 'light_luxury');
  const strip = c.elements.find((e) => e.id === 'strip');
  // 2 panels, margin .06, gap .03 -> panelW = (1 - .12 - .03)/2 = .425
  assert.ok(Math.abs(strip.panelW - 0.425) < 1e-9);
  assert.ok(strip.blocks[0].panelPos.y > 0 && strip.blocks[0].panelPos.y < 0.5);  // centered
});

test('seedLayout is deterministic and preserves a double pill', () => {
  let c = defaultComposition('before_after');
  c = structuredClone(c);
  c.elements.find((e) => e.id === 'strip').blocks[0].pill = { width: 'double' };
  const s1 = seedLayout(c);
  const s2 = seedLayout(s1);
  assert.deepEqual(s1, s2);                                          // idempotent shape
  assert.equal(s1.elements.find((e) => e.id === 'strip').blocks[0].pill.width, 'double');
});

test('ensureLayout only seeds when positions are absent', () => {
  const raw = { version: 1, size: 'square', theme: 'dark_premium', elements: [
    { id: 'title', type: 'title', headline: { text: 'X' }, subline: { text: 'Y' } },
    { id: 'strip', type: 'photoStrip', blocks: [{ photo: null, badge: 1, label: 'A' }] },
    { id: 'doctor', type: 'doctorName', text: 'DR. Z' },
  ] };
  assert.equal(hasLayout(raw), false);
  const seeded = ensureLayout(raw);
  assert.equal(hasLayout(seeded), true);
  assert.equal(ensureLayout(seeded), seeded);                        // no re-seed (same reference)
});
