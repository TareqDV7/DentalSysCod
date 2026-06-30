// render.js — pure structural renderer: composition -> native-size DOM stage.
// INLINE STYLES ONLY (the foreignObject export context can't reach <style>).
// Theme tokens (bg, card, badge, divider, fonts) applied via themeTokens().

import { themeTokens } from './themes.js';

export const EXPORT_PX = {
  square: [1080, 1080],
  portrait: [1080, 1350],
  story: [1080, 1920],
};

const px = (n) => `${n}px`;
const setStyle = (el, styles) => { Object.assign(el.style, styles); return el; };

// Arabic-script ranges: any run containing these must render in Cairo (the only
// bundled face with Arabic glyphs) regardless of the theme's Latin display font.
const ARABIC_RE = /[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]/;
const FONT_FALLBACK = 'system-ui, "Segoe UI", sans-serif';

function fontStack(font, text) {
  if (text && ARABIC_RE.test(text)) {
    return font ? `"Cairo", "${font}", ${FONT_FALLBACK}` : `"Cairo", ${FONT_FALLBACK}`;
  }
  return font ? `"${font}", ${FONT_FALLBACK}` : 'inherit';
}

function typoStyle(t, text) {
  if (!t) return {};
  return {
    fontFamily: fontStack(t.font, text),
    color: t.color || '#ffffff',
    fontSize: px(t.size || 32),
    fontWeight: String(t.weight || 600),
    letterSpacing: px(t.letterSpacing || 0),
    lineHeight: '1.2',
    margin: '0',
  };
}

const SVG_NS = 'http://www.w3.org/2000/svg';
// Simple outlined tooth (refine glyph in QA if needed — exports as inline SVG).
const TOOTH_PATH =
  'M12 2.2c-1.7 0-2.6.9-4.4.9S4.6 2.2 3.4 4c-1.1 2.8-.2 6.7.8 10.6.5 2 .9 5.6 2.3 5.6 ' +
  '1.1 0 1.2-2.8 1.9-4.8.3-.9.8-1.4 1.6-1.4s1.3.5 1.6 1.4c.7 2 .8 4.8 1.9 4.8 1.4 0 ' +
  '1.8-3.6 2.3-5.6 1-3.9 1.9-7.8.8-10.6-1.2-1.8-2.4-.9-4.2-.9s-2.7-.9-4.4-.9z';

function toothIcon(color) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', '46');
  svg.setAttribute('height', '46');
  const path = document.createElementNS(SVG_NS, 'path');
  path.setAttribute('d', TOOTH_PATH);
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', color);
  path.setAttribute('stroke-width', '1.4');
  path.setAttribute('stroke-linejoin', 'round');
  svg.appendChild(path);
  return svg;
}

function buildDivider(theme) {
  const row = document.createElement('div');
  setStyle(row, {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    gap: '20px', marginTop: '20px',
  });
  const rule = () => {
    const r = document.createElement('div');
    setStyle(r, { height: '1px', width: '130px', background: theme.divider.color, opacity: '.75' });
    return r;
  };
  row.appendChild(rule());
  row.appendChild(toothIcon(theme.divider.color));
  row.appendChild(rule());
  return row;
}

function buildTitle(el, theme) {
  const box = document.createElement('div');
  setStyle(box, {
    position: 'absolute', left: '0', right: '0',
    top: `${(el.y ?? 0.10) * 100}%`, transform: 'translateY(-50%)',
    textAlign: el.align || 'center', padding: '0 6%', boxSizing: 'border-box',
  });
  const head = document.createElement('div');
  head.setAttribute('data-ps-headline', '');
  head.textContent = el.headline ? (el.headline.text || '') : '';
  setStyle(head, typoStyle({ ...theme.headline, ...el.headline }, head.textContent));
  const sub = document.createElement('div');
  sub.textContent = el.subline ? (el.subline.text || '') : '';
  setStyle(sub, typoStyle({ ...theme.subline, ...el.subline }, sub.textContent));
  box.appendChild(head);
  box.appendChild(sub);
  if (theme.divider && theme.divider.enabled) box.appendChild(buildDivider(theme));
  return box;
}

function buildCard(b, el, theme) {
  const card = document.createElement('div');
  setStyle(card, {
    position: 'relative', flex: '1 1 0', display: 'flex',
    flexDirection: 'column', gap: '14px', alignItems: 'center', minWidth: '0',
  });
  const frame = document.createElement('div');
  setStyle(frame, {
    position: 'relative', width: '100%', aspectRatio: '1 / 1',
    borderRadius: px(theme.card.borderRadius), overflow: 'hidden',
    border: theme.card.border, boxShadow: theme.card.boxShadow,
    background: theme.card.background,
  });
  if (b.photo) {
    const img = document.createElement('img');
    img.src = b.photo;
    img.alt = '';
    setStyle(img, { width: '100%', height: '100%', objectFit: 'cover', display: 'block' });
    frame.appendChild(img);
  }
  const badge = document.createElement('div');
  badge.textContent = String(b.badge || 0);
  setStyle(badge, {
    position: 'absolute', top: '14px', left: '14px', width: '52px', height: '52px',
    borderRadius: theme.badge.shape === 'circle' ? '50%' : '10px',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: theme.badge.background, color: theme.badge.color,
    border: theme.badge.border, fontWeight: '700', fontSize: '26px',
  });
  frame.appendChild(badge);
  const label = document.createElement('div');
  label.textContent = b.label || '';
  setStyle(label, { ...typoStyle({ ...theme.label, ...el.labelStyle }, label.textContent), textAlign: 'center' });
  card.appendChild(frame);
  card.appendChild(label);
  return card;
}

function buildStrip(el, theme) {
  const wrap = document.createElement('div');
  const blocks = el.blocks || [];
  const isGrid = el.layout === 'grid' || blocks.length > 3;
  setStyle(wrap, {
    position: 'absolute', left: '6%', right: '6%', top: '50%',
    transform: 'translateY(-50%)',
    display: isGrid ? 'grid' : 'flex',
    gridTemplateColumns: isGrid ? 'repeat(2, minmax(0, 1fr))' : '',
    gap: '32px', justifyItems: 'stretch', alignItems: 'stretch',
  });
  for (const b of blocks) wrap.appendChild(buildCard(b, el, theme));
  return wrap;
}

function buildDoctor(el, theme) {
  const t = { ...theme.doctor, ...el };   // theme defaults; element values override
  const box = document.createElement('div');
  box.textContent = el.text || '';
  setStyle(box, {
    position: 'absolute', left: '0', right: '0',
    top: `${(el.y ?? 0.93) * 100}%`, transform: 'translateY(-50%)',
    textAlign: el.align || 'center', textTransform: 'uppercase',
    fontFamily: fontStack(t.font, box.textContent),
    color: t.color || '#c9a86a',
    fontSize: px(t.size || 34),
    fontWeight: String(t.weight || 700),
    letterSpacing: px(t.letterSpacing || 4),
  });
  return box;
}

export function renderComposition(comp) {
  const [w, h] = EXPORT_PX[comp.size] || EXPORT_PX.square;
  const theme = themeTokens(comp.theme);
  const stage = document.createElement('div');
  stage.setAttribute('data-ps-stage', '');
  setStyle(stage, {
    position: 'relative', width: px(w), height: px(h), overflow: 'hidden',
    background: theme.bg,
    fontFamily: 'system-ui, "Segoe UI", sans-serif',
  });
  for (const el of (comp.elements || [])) {
    if (el.type === 'title') stage.appendChild(buildTitle(el, theme));
    else if (el.type === 'photoStrip') stage.appendChild(buildStrip(el, theme));
    else if (el.type === 'doctorName') stage.appendChild(buildDoctor(el, theme));
  }
  return stage;
}
