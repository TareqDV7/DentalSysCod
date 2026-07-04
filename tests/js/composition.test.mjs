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
  // centered row: 4*250+3*16=1048 -> start 16 (tolerance: (1-rowW)/2 drifts ~1e-17 from 16/1080)
  assert.ok(Math.abs(strip.blocks[0].panelPos.x - 16 / 1080) < 1e-9);
  assert.ok(Math.abs(strip.blocks[1].panelPos.x - (16 + 266) / 1080) < 1e-9);   // panelW+gap = 266
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

import { getPosition, setPosition, nudgePosition } from '../../static/post_studio/composition.js';

test('setPosition writes each ref field immutably and clamps to [0,1]', () => {
  const c = defaultComposition('before_after');
  const t = setPosition(c, 'title', { x: 0.4, y: 0.2 });
  assert.deepEqual(t.elements.find((e) => e.id === 'title').pos, { x: 0.4, y: 0.2 });
  assert.notDeepEqual(c.elements.find((e) => e.id === 'title').pos, { x: 0.4, y: 0.2 }); // input intact
  const p = setPosition(c, 'panel:1', { x: 1.5, y: -0.3 });                              // clamps
  assert.deepEqual(p.elements.find((e) => e.id === 'strip').blocks[1].panelPos, { x: 1, y: 0 });
  const q = setPosition(c, 'pill:0', { x: 0.1, y: 0.7 });
  assert.deepEqual(q.elements.find((e) => e.id === 'strip').blocks[0].pillPos, { x: 0.1, y: 0.7 });
  assert.throws(() => setPosition(c, 'nope:9', { x: 0, y: 0 }));
});

test('nudgePosition adds a pixel delta as a canvas fraction', () => {
  const c = setPosition(defaultComposition('before_after'), 'doctor', { x: 0.5, y: 0.5 });
  const n = nudgePosition(c, 'doctor', 10, -20, [1080, 1080]);
  const pos = n.elements.find((e) => e.id === 'doctor').pos;
  assert.ok(Math.abs(pos.x - (0.5 + 10 / 1080)) < 1e-9);
  assert.ok(Math.abs(pos.y - (0.5 - 20 / 1080)) < 1e-9);
});

test('getPosition reads the correct field per ref', () => {
  const c = defaultComposition('before_after');
  assert.deepEqual(getPosition(c, 'panel:0'),
    c.elements.find((e) => e.id === 'strip').blocks[0].panelPos);
  assert.deepEqual(getPosition(c, 'title'), c.elements.find((e) => e.id === 'title').pos);
});

test('deserialize seeds a legacy post that has no positions', () => {
  const legacy = JSON.stringify({ version: 1, size: 'square', theme: 'dark_premium', elements: [
    { id: 'title', type: 'title', headline: { text: 'Old' }, subline: { text: 'Post' } },
    { id: 'strip', type: 'photoStrip', blocks: [{ photo: null, badge: 1, label: 'A' }] },
    { id: 'doctor', type: 'doctorName', text: 'DR. X' },
  ] });
  const c = deserialize(legacy);
  assert.equal(hasLayout(c), true);
  assert.ok(c.elements.find((e) => e.id === 'strip').blocks[0].panelPos);
});

import {
  hasBlockStyle, seedBlockStyle,
} from '../../static/post_studio/composition.js';

test('seedLayout stamps per-block panelW/panelH/labelStyle', () => {
  const c = defaultComposition('before_after');   // dark_premium default
  const strip = c.elements.find((e) => e.id === 'strip');
  for (const b of strip.blocks) {
    assert.equal(b.panelW, 250 / 1080);
    assert.equal(b.panelH, 320 / 1080);
    assert.ok(b.labelStyle && b.labelStyle.font);
  }
  assert.equal(hasBlockStyle(c), true);
});

test('ensureLayout migrates a P4b-1-shape comp: fills per-block size/style, preserves existing positions', () => {
  const legacy = {
    version: 1, size: 'square', theme: 'dark_premium',
    elements: [
      { id: 'title', type: 'title', pos: { x: 0.5, y: 0.2 },
        headline: { text: 'X' }, subline: { text: 'Y' } },
      { id: 'strip', type: 'photoStrip', panelW: 0.3, panelH: 0.35, gap: 16 / 1080,
        labelStyle: { font: 'Manrope', size: 28, weight: 600, color: '#cfd8e3' },
        blocks: [
          { photo: null, badge: 1, label: 'A',
            panelPos: { x: 0.1, y: 0.4 }, pillPos: { x: 0.1, y: 0.7 }, pill: { width: 'single' } },
          { photo: null, badge: 2, label: 'B',
            panelPos: { x: 0.45, y: 0.4 }, pillPos: { x: 0.45, y: 0.7 }, pill: { width: 'single' } },
        ] },
      { id: 'doctor', type: 'doctorName', pos: { x: 0.5, y: 0.9 }, text: 'DR. X' },
    ],
  };
  assert.equal(hasBlockStyle(legacy), false);
  const c = ensureLayout(legacy);
  const strip = c.elements.find((e) => e.id === 'strip');
  // dragged positions untouched
  assert.deepEqual(strip.blocks[0].panelPos, { x: 0.1, y: 0.4 });
  assert.deepEqual(strip.blocks[1].pillPos, { x: 0.45, y: 0.7 });
  // per-block size/style filled in
  for (const b of strip.blocks) {
    assert.ok(b.panelW != null && b.panelH != null);
    assert.ok(b.labelStyle && b.labelStyle.font);
  }
  assert.equal(hasBlockStyle(c), true);
});

test('seedBlockStyle never overwrites an existing per-block value', () => {
  const c = defaultComposition('before_after');
  const strip = c.elements.find((e) => e.id === 'strip');
  strip.blocks[0].panelW = 0.5;   // pretend block 0 was already resized
  const seeded = seedBlockStyle(c);
  const strip2 = seeded.elements.find((e) => e.id === 'strip');
  assert.equal(strip2.blocks[0].panelW, 0.5);
  assert.equal(strip2.blocks[1].panelW, 250 / 1080);   // still gets the default
});
