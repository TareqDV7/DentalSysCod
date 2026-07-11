// render.js — pure structural renderer: composition -> native-size DOM stage.
// INLINE STYLES ONLY (the foreignObject export context can't reach <style>).
// Theme tokens (bg, card, badge, divider, fonts) applied via themeTokens().

import { themeTokens } from './themes.js';
import { ensureLayout } from './composition.js';

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
// Outlined tooth — double-cusp crown (with a center notch), a shoulder that
// pinches inward toward the neck, and a forked root. Matches the reference
// go.png divider glyph; verified against it via a side-by-side render (see
// docs/superpowers/ for the Post Studio design notes).
const TOOTH_PATH =
  'M8.8,4.2 C7.6,4.2 5.6,5.3 4.9,7.6 C4.4,10.3 5.6,11.9 6.3,12.6 C7.0,13.3 7.4,14.8 7.6,16.0 ' +
  'C8.1,17.4 8.3,20.6 9.3,20.6 C10.1,20.6 10.2,17.6 10.8,15.9 C11.1,15.0 11.5,14.5 12,14.5 ' +
  'C12.5,14.5 12.9,15.0 13.2,15.9 C13.8,17.6 13.9,20.6 14.7,20.6 C15.7,20.6 15.9,17.4 16.4,16.0 ' +
  'C16.6,14.8 17.0,13.3 17.7,12.6 C18.4,11.9 19.6,10.3 19.1,7.6 C18.4,5.3 16.4,4.2 15.2,4.2 ' +
  'C14.2,4.2 13.6,5.6 12,5.6 C10.4,5.6 9.8,4.2 8.8,4.2 Z';

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
  row.setAttribute('data-ps-divider', '');
  setStyle(row, {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    gap: '20px', marginTop: '20px',
  });
  const rule = () => {
    const r = document.createElement('div');
    // Geometry is token-driven so retuning one theme's divider never leaks into
    // another. Defaults reproduce the original 1px/130px/.75 line for any theme
    // that doesn't override them (e.g. light_luxury).
    setStyle(r, {
      height: theme.divider.thickness || '1px',
      width: theme.divider.lineWidth || '130px',
      background: theme.divider.color,
      opacity: theme.divider.lineOpacity || '.75',
    });
    return r;
  };
  row.appendChild(rule());
  row.appendChild(toothIcon(theme.divider.color));
  row.appendChild(rule());
  return row;
}

const WAVE_BAND = 140;        // px tall band anchored to the stage bottom
const WAVE_WIDTH = 1080;      // canvas reference width (all sizes are 1080 wide)

function sinePath(baseY, amp, freq, step = 8) {
  let d = `M 0 ${(baseY).toFixed(1)}`;
  for (let x = step; x <= WAVE_WIDTH; x += step) {
    const y = baseY + amp * Math.sin(freq * x);
    d += ` L ${x} ${y.toFixed(1)}`;
  }
  return d;
}

function buildWaveFooter(theme) {
  const wf = theme.waveFooter;
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('data-ps-wave', '');
  svg.setAttribute('viewBox', `0 0 ${WAVE_WIDTH} ${WAVE_BAND}`);
  svg.setAttribute('preserveAspectRatio', 'none');
  setStyle(svg, {
    position: 'absolute', left: '0', bottom: '0',
    width: '100%', height: px(WAVE_BAND), pointerEvents: 'none',
  });
  // Spec offsets (985/1015/1045 in a 1080 canvas) measured from the bottom,
  // mapped into the local band so the wave is bottom-anchored at any size.
  const baseYs = [45, 75, 105];
  wf.layers.forEach((layer, i) => {
    const path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', sinePath(baseYs[i] ?? 75, layer.amp, layer.freq));
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', wf.color);
    path.setAttribute('stroke-width', '2');
    path.setAttribute('opacity', String(layer.opacity));
    svg.appendChild(path);
  });
  return svg;
}

// Unbounded headline/subline text has no natural height limit — long input
// wraps to as many lines as it needs, which pushes the vertically-centered
// title box up into the canvas top edge (hard clip) or down into the photo
// row (panels paint after the title, so overflow is silently hidden behind
// them, not just clipped). Clamping to a fixed line count keeps the title
// box height predictable so the fixed titleY/panelRowY layout tokens stay
// valid regardless of how much text the user types; excess text truncates
// with an ellipsis instead of disappearing under a panel.
function clampLines(n) {
  return {
    display: '-webkit-box', WebkitLineClamp: String(n), WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
  };
}

function buildTitle(el, theme, W, H) {
  const pos = el.pos || { x: 0.5, y: 0.1 };
  const box = document.createElement('div');
  setStyle(box, {
    position: 'absolute', left: px(pos.x * W), top: px(pos.y * H),
    transform: 'translate(-50%, -50%)', maxWidth: px(0.88 * W),
    textAlign: el.align || 'center', boxSizing: 'border-box',
  });
  const head = document.createElement('div');
  head.setAttribute('data-ps-headline', '');
  head.setAttribute('data-ps-el', 'title.headline');
  head.textContent = el.headline ? (el.headline.text || '') : '';
  setStyle(head, { ...typoStyle({ ...theme.headline, ...el.headline }, head.textContent), ...clampLines(2) });
  const sub = document.createElement('div');
  sub.setAttribute('data-ps-el', 'title.subline');
  sub.textContent = el.subline ? (el.subline.text || '') : '';
  setStyle(sub, { ...typoStyle({ ...theme.subline, ...el.subline }, sub.textContent), ...clampLines(2) });
  box.appendChild(head);
  box.appendChild(sub);
  if (theme.divider && theme.divider.enabled) box.appendChild(buildDivider(theme));
  return box;
}

function buildDoctor(el, theme, W, H) {
  const t = { ...theme.doctor, ...el };
  const pos = el.pos || { x: 0.5, y: 0.93 };
  const box = document.createElement('div');
  box.setAttribute('data-ps-el', 'doctor');
  box.textContent = el.text || '';
  setStyle(box, {
    position: 'absolute', left: px(pos.x * W), top: px(pos.y * H),
    transform: 'translate(-50%, -50%)', textAlign: el.align || 'center',
    textTransform: 'uppercase',
    fontFamily: fontStack(t.font, box.textContent),
    color: t.color || '#c9a86a',
    fontSize: px(t.size || 34),
    fontWeight: String(t.weight || 700),
    letterSpacing: px(t.letterSpacing || 4),
  });
  return box;
}

function buildStrip(el, theme, W, H) {
  const wrap = document.createElement('div');
  setStyle(wrap, { position: 'absolute', left: '0', top: '0', width: '100%', height: '100%',
    pointerEvents: 'none' });
  const isPill = theme.label && theme.label.style === 'pill';
  const blocks = el.blocks || [];
  blocks.forEach((b, i) => {
    wrap.appendChild(buildPanel(b, el, theme, i, W, H, isPill));
    const prevDouble = blocks[i - 1] && blocks[i - 1].pill && blocks[i - 1].pill.width === 'double';
    if (isPill && !prevDouble) {
      wrap.appendChild(buildPill(b, el, blocks[i + 1], theme, i, W, H));
    }
  });
  return wrap;
}

function buildPanel(b, el, theme, index, W, H, isPill) {
  const pos = b.panelPos || { x: 0, y: 0 };
  const panelW = b.panelW != null ? b.panelW : (el.panelW || 0.2);
  const panelH = b.panelH != null ? b.panelH : (el.panelH || 0.2);
  const card = document.createElement('div');
  card.setAttribute('data-ps-block', String(index));
  setStyle(card, {
    position: 'absolute', left: px(pos.x * W), top: px(pos.y * H),
    width: px(panelW * W), pointerEvents: 'auto',
    display: 'flex', flexDirection: 'column', gap: '14px', alignItems: 'center',
  });
  const frame = document.createElement('div');
  frame.setAttribute('data-ps-frame', '');
  setStyle(frame, {
    position: 'relative', width: '100%', height: px(panelH * H),
    borderRadius: px(theme.card.borderRadius), overflow: 'hidden',
    border: theme.card.border, boxShadow: theme.card.boxShadow,
    background: theme.card.background,
  });
  if (b.photo) {
    const img = document.createElement('img');
    img.src = b.photo; img.alt = '';
    setStyle(img, { width: '100%', height: '100%', objectFit: 'cover', display: 'block' });
    frame.appendChild(img);
  }
  if (!isPill) {
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
  }
  card.appendChild(frame);
  if (!isPill) {
    const label = document.createElement('div');
    label.textContent = b.label || '';
    setStyle(label, { ...typoStyle({ ...theme.label, ...b.labelStyle }, label.textContent), textAlign: 'center' });
    card.appendChild(label);
  }
  return card;
}

function buildPill(b, el, nextBlock, theme, index, W, H) {
  const pos = b.pillPos || { x: 0, y: 0 };
  const ownW = (b.panelW != null ? b.panelW : (el.panelW || 0.2)) * W;
  // 'double' only has a neighbor's slot to cover when a next block exists;
  // a trailing 'double' (e.g. left over from a reorder/remove that made this
  // the last block) has nothing to reach for, so it renders as single-width
  // rather than guessing at an off-canvas phantom neighbor.
  const isDouble = !!(b.pill && b.pill.width === 'double' && nextBlock);
  let pillW = ownW;
  if (isDouble) {
    const nextPos = nextBlock.panelPos || { x: 0, y: 0 };
    const nextW = (nextBlock.panelW != null ? nextBlock.panelW : (el.panelW || 0.2)) * W;
    pillW = (nextPos.x * W + nextW) - (pos.x * W);
  }
  const pill = document.createElement('div');
  pill.setAttribute('data-ps-pill', '');
  pill.setAttribute('data-ps-pill-block', String(index));
  setStyle(pill, {
    position: 'absolute', left: px(pos.x * W), top: px(pos.y * H),
    width: px(pillW), height: '56px', pointerEvents: 'auto',
    display: 'flex', alignItems: 'center', gap: '10px', padding: '0 16px',
    boxSizing: 'border-box', borderRadius: '28px', border: theme.pill.border,
  });
  const circle = document.createElement('div');
  circle.textContent = String(b.badge || 0);
  setStyle(circle, {
    flex: '0 0 auto', width: '26px', height: '26px', borderRadius: '50%',
    border: theme.pill.circleBorder, color: theme.label.color || '#F5F5F0',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontFamily: fontStack(theme.label.font, ''), fontWeight: '700', fontSize: '19px',
  });
  const text = document.createElement('div');
  text.textContent = b.label || '';
  setStyle(text, {
    ...typoStyle({ ...theme.label, ...b.labelStyle, color: theme.pill.color || theme.label.color }, b.label),
    flex: '1 1 auto', textAlign: isDouble ? 'center' : 'left',
  });
  pill.appendChild(circle);
  pill.appendChild(text);
  return pill;
}

export function renderComposition(comp) {
  comp = ensureLayout(comp);
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
    if (el.type === 'title') stage.appendChild(buildTitle(el, theme, w, h));
    else if (el.type === 'photoStrip') stage.appendChild(buildStrip(el, theme, w, h));
    else if (el.type === 'doctorName') stage.appendChild(buildDoctor(el, theme, w, h));
  }
  if (theme.waveFooter && theme.waveFooter.enabled) stage.appendChild(buildWaveFooter(theme));
  return stage;
}
