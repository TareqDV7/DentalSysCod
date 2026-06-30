import { test } from 'node:test';
import assert from 'node:assert/strict';
import { THEMES, THEME_OPTIONS, themeTokens }
  from '../../static/post_studio/themes.js';

const NAMES = ['dark_premium', 'light_luxury', 'clinical_premium', 'bold_editorial'];

test('THEME_OPTIONS lists the four themes with bilingual labels', () => {
  assert.deepEqual(THEME_OPTIONS.map((o) => o.id), NAMES);
  for (const o of THEME_OPTIONS) {
    assert.ok(o.label && o.label_ar, `${o.id} needs label + label_ar`);
  }
});

test('every theme has the full token shape', () => {
  for (const name of NAMES) {
    const t = THEMES[name];
    assert.ok(t, `missing theme ${name}`);
    assert.ok(t.bg, `${name}.bg`);
    for (const role of ['headline', 'subline', 'label', 'doctor']) {
      const r = t[role];
      for (const k of ['font', 'size', 'weight', 'color', 'letterSpacing']) {
        assert.ok(r[k] !== undefined, `${name}.${role}.${k} missing`);
      }
    }
    assert.equal(typeof t.card.borderRadius, 'number');
    assert.ok(['circle', 'square'].includes(t.badge.shape));
    assert.equal(typeof t.divider.enabled, 'boolean');
    assert.ok(t.accent);
  }
});

test('dark_premium matches Navy & Gold: Poppins, gold #C6A274, navy radial, pill labels, wave', () => {
  const t = THEMES.dark_premium;
  assert.equal(t.headline.font, 'Poppins');
  assert.equal(t.headline.size, 78);
  assert.equal(t.headline.weight, 700);
  assert.equal(t.headline.color, '#F5F5F0');
  assert.equal(t.subline.font, 'Poppins');
  assert.equal(t.subline.size, 58);
  assert.equal(t.subline.color, '#C6A274');     // gold
  assert.equal(t.doctor.font, 'Poppins');
  assert.equal(t.doctor.size, 52);
  assert.equal(t.doctor.color, '#C6A274');
  assert.equal(t.accent, '#C6A274');
  assert.ok(t.bg.includes('radial-gradient'));
  assert.ok(t.bg.includes('#0C1E3A') && t.bg.includes('#040E20'));
  assert.equal(t.card.borderRadius, 14);
  assert.equal(t.card.aspect, '250 / 320');
  assert.equal(t.card.boxShadow, 'none');
  assert.equal(t.label.style, 'pill');
  assert.ok(t.pill && t.pill.border && t.pill.circleBorder);
  assert.equal(t.divider.enabled, true);
  assert.equal(t.divider.icon, 'tooth');
  assert.equal(t.waveFooter.enabled, true);
  assert.equal(t.waveFooter.layers.length, 3);
});

test('light_luxury uses a serif headline', () => {
  assert.equal(THEMES.light_luxury.headline.font, 'Playfair Display');
});

test('themeTokens falls back to dark_premium for unknown names', () => {
  assert.equal(themeTokens('nope'), THEMES.dark_premium);
  assert.equal(themeTokens('clinical_premium'), THEMES.clinical_premium);
});
