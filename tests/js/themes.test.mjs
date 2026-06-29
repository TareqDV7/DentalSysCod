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

test('dark_premium matches go.png: sans white headline, gold accents, tooth divider', () => {
  const t = THEMES.dark_premium;
  assert.equal(t.headline.font, 'Manrope');        // bold sans, per go.png
  assert.equal(t.headline.color, '#ffffff');
  assert.equal(t.subline.color, '#c9a86a');        // gold subline (go.png)
  assert.equal(t.doctor.color, '#c9a86a');
  assert.equal(t.divider.enabled, true);
  assert.equal(t.divider.icon, 'tooth');
  assert.ok(t.bg.includes('radial-gradient'));     // navy glow, not a flat fill
});

test('light_luxury uses a serif headline', () => {
  assert.equal(THEMES.light_luxury.headline.font, 'Playfair Display');
});

test('themeTokens falls back to dark_premium for unknown names', () => {
  assert.equal(themeTokens('nope'), THEMES.dark_premium);
  assert.equal(themeTokens('clinical_premium'), THEMES.clinical_premium);
});
