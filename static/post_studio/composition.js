// Pure, DOM-free composition state for Post Studio.
// Single source of truth for the template_json shape. ESM so it loads in
// node --test AND in the WebView (<script type="module">). Never mutates inputs.

import { themeTokens, themeLayout } from './themes.js';

export const MAX_BLOCKS = 6;
export const SIZES = ['square', 'portrait', 'story'];
export const TEMPLATES = ['before_after', 'multi_phase', 'quad_grid', 'single_feature'];

const DEFAULT_THEME = 'dark_premium';

// Element factory helpers — geometry/typography here are structural defaults
// only; P3 themes restyle them. Positions are fractional (0–1), size-independent.
function titleElement() {
  return {
    id: 'title', type: 'title', x: 0.5, y: 0.10, align: 'center',
    headline: { text: 'Procedure Title', font: 'Playfair Display', size: 64, weight: 700, color: '#ffffff', letterSpacing: 0 },
    subline: { text: 'Subtitle', font: 'Manrope', size: 40, weight: 500, color: '#5fd3c8', letterSpacing: 0 },
    icon: null,
  };
}

function block(label) {
  return { photo: null, badge: 0, label };
}

function stripElement(labels, layout) {
  const blocks = labels.map((label) => block(label));
  return renumber({
    id: 'strip', type: 'photoStrip', layout: layout || 'row',
    blocks,
    labelStyle: { font: 'Manrope', size: 28, weight: 600, color: '#cfd8e3' },
  });
}

function doctorElement(doctorName) {
  return {
    id: 'doctor', type: 'doctorName', x: 0.5, y: 0.93, align: 'center',
    text: doctorName || '',
    font: 'Manrope', size: 34, weight: 700, color: '#c9a227', letterSpacing: 4,
  };
}

// Canvas pixel dims per size (mirrors render.EXPORT_PX; kept here so the DOM-free
// layout engine has no dependency on render.js).
export const CANVAS_DIMS = { square: [1080, 1080], portrait: [1080, 1350], story: [1080, 1920] };

function parseAspect(card) {
  // card.aspect like '250 / 320' (W / H); default square 1:1.
  if (!card || !card.aspect) return { w: 1, h: 1 };
  const parts = String(card.aspect).split('/').map((s) => parseFloat(s.trim()));
  if (parts.length === 2 && parts[0] > 0 && parts[1] > 0) return { w: parts[0], h: parts[1] };
  return { w: 1, h: 1 };
}

// Returns a NEW comp with every positionable element's coordinates recomputed
// from the active theme's layout tokens. Single centered row for all panel counts.
export function seedLayout(comp) {
  const next = structuredClone(comp);
  const L = themeLayout(next.theme);
  const [W, H] = CANVAS_DIMS[next.size] || CANVAS_DIMS.square;
  const title = next.elements.find((e) => e.id === 'title');
  const strip = next.elements.find((e) => e.id === 'strip');
  const doctor = next.elements.find((e) => e.id === 'doctor');
  if (title) title.pos = { x: 0.5, y: L.titleY };
  if (doctor) doctor.pos = { x: 0.5, y: L.doctorY };
  if (strip) {
    const n = strip.blocks.length || 1;
    const asp = parseAspect(themeTokens(next.theme).card);
    const panelW = L.panelW != null ? L.panelW : (1 - 2 * L.margin - (n - 1) * L.gap) / n;
    const panelH = L.panelH != null ? L.panelH : panelW * (W / H) * (asp.h / asp.w);
    const rowW = n * panelW + (n - 1) * L.gap;
    const startX = (1 - rowW) / 2;   // centre the row for any panel count
    const panelY = L.panelRowY != null ? L.panelRowY : 0.5 - panelH / 2;
    const pillY = L.pillRowY != null ? L.pillRowY : panelY + panelH + L.gap;
    strip.panelW = panelW;
    strip.panelH = panelH;
    strip.gap = L.gap;
    strip.blocks = strip.blocks.map((b, i) => ({
      ...b,
      panelPos: { x: startX + i * (panelW + L.gap), y: panelY },
      pillPos: { x: startX + i * (panelW + L.gap), y: pillY },
      pill: { width: (b.pill && b.pill.width) || 'single' },
    }));
  }
  return next;
}

export function hasLayout(comp) {
  const title = (comp.elements || []).find((e) => e.id === 'title');
  return !!(title && title.pos);
}

export function ensureLayout(comp) {
  return hasLayout(comp) ? comp : seedLayout(comp);
}

// Returns a NEW strip whose blocks are renumbered 1..n (badges follow order).
export function renumber(strip) {
  const next = structuredClone(strip);
  next.blocks = next.blocks.map((b, i) => ({ ...b, badge: i + 1 }));
  return next;
}

const SEEDS = {
  before_after: { labels: ['Before Treatment', 'After Treatment'], layout: 'row' },
  multi_phase: { labels: ['Before', 'During', 'After'], layout: 'row' },
  quad_grid: { labels: ['Angle 1', 'Angle 2', 'Angle 3', 'Angle 4'], layout: 'grid' },
  single_feature: { labels: ['Result'], layout: 'row' },
};

export function defaultComposition(template, opts = {}) {
  const seed = SEEDS[template];
  if (!seed) throw new Error(`unknown template: ${template}`);
  const base = {
    version: 1,
    size: 'square',
    theme: DEFAULT_THEME,
    elements: [
      titleElement(),
      stripElement(seed.labels, seed.layout),
      doctorElement(opts.doctorName),
    ],
  };
  return applyTheme(base, opts.theme || DEFAULT_THEME);
}

export function serialize(comp) {
  return JSON.stringify(comp);
}

export function deserialize(json) {
  const c = typeof json === 'string' ? JSON.parse(json) : json;
  if (c.version !== 1) throw new Error(`unsupported version: ${c.version}`);
  if (!SIZES.includes(c.size)) throw new Error(`invalid size: ${c.size}`);
  return ensureLayout(structuredClone(c));
}

// Returns a NEW comp with `themeName` applied: each element's typography fields
// are set from the theme tokens; text, photos, positions, badges, labels are
// preserved. v1 behavior: switching themes resets per-element typography.
export function applyTheme(comp, themeName) {
  const t = themeTokens(themeName);
  const next = structuredClone(comp);
  next.theme = themeName;
  for (const el of next.elements) {
    if (el.type === 'title') {
      el.headline = { ...el.headline, ...t.headline };
      el.subline = { ...el.subline, ...t.subline };
    } else if (el.type === 'photoStrip') {
      el.labelStyle = { ...el.labelStyle, ...t.label };
    } else if (el.type === 'doctorName') {
      Object.assign(el, t.doctor);
    }
  }
  return seedLayout(next);
}

// Returns a NEW composition with `mutate(blocks)` applied to a copy of the
// strip's blocks, then badges renumbered. Never touches the input.
function withBlocks(comp, mutate) {
  const next = structuredClone(comp);
  const strip = next.elements.find((e) => e.id === 'strip');
  if (!strip) throw new Error('composition has no photoStrip');
  const blocks = strip.blocks.slice();
  mutate(blocks);
  strip.blocks = blocks;
  const renumbered = renumber(strip);
  next.elements = next.elements.map((e) => (e.id === 'strip' ? renumbered : e));
  return next;
}

function freshBlock(label) {
  return { photo: null, badge: 0, label: label || 'New' };
}

export function addBlock(comp, label) {
  return withBlocks(comp, (blocks) => {
    if (blocks.length >= MAX_BLOCKS) throw new Error(`max ${MAX_BLOCKS} blocks`);
    blocks.push(freshBlock(label));
  });
}

export function insertBlock(comp, index, label) {
  return withBlocks(comp, (blocks) => {
    if (blocks.length >= MAX_BLOCKS) throw new Error(`max ${MAX_BLOCKS} blocks`);
    const i = Math.max(0, Math.min(index, blocks.length));
    blocks.splice(i, 0, freshBlock(label));
  });
}

export function removeBlock(comp, index) {
  return withBlocks(comp, (blocks) => {
    if (index < 0 || index >= blocks.length) throw new Error(`bad index ${index}`);
    blocks.splice(index, 1);
  });
}

export function reorderBlock(comp, from, to) {
  return withBlocks(comp, (blocks) => {
    if (from < 0 || from >= blocks.length) throw new Error(`bad from ${from}`);
    const [moved] = blocks.splice(from, 1);
    const dest = Math.max(0, Math.min(to, blocks.length));
    blocks.splice(dest, 0, moved);
  });
}

export const SIZE_MIN = 16;
export const SIZE_MAX = 160;
const HEX_RE = /^#[0-9a-fA-F]{6}$/;

function clampSize(n) {
  const v = Math.round(Number(n));
  if (!Number.isFinite(v)) return null;
  return Math.max(SIZE_MIN, Math.min(SIZE_MAX, v));
}

// A selectable text run (has its own .text): headline, subline, doctor.
function textRunTarget(comp, ref) {
  const title = comp.elements.find((e) => e.id === 'title');
  const doctor = comp.elements.find((e) => e.id === 'doctor');
  if (ref === 'title.headline') return title && title.headline;
  if (ref === 'title.subline') return title && title.subline;
  if (ref === 'doctor') return doctor;
  return null;
}

// A typography target — text runs plus the shared label style.
function typoTarget(comp, ref) {
  if (ref === 'strip.label') {
    const strip = comp.elements.find((e) => e.id === 'strip');
    return strip && strip.labelStyle;
  }
  return textRunTarget(comp, ref);
}

export function setText(comp, ref, value) {
  const next = structuredClone(comp);
  const target = textRunTarget(next, ref);
  if (!target) throw new Error(`bad text ref: ${ref}`);
  target.text = String(value);
  return next;
}

export function setTypography(comp, ref, patch) {
  const next = structuredClone(comp);
  const target = typoTarget(next, ref);
  if (!target) throw new Error(`bad typography ref: ${ref}`);
  if (patch.font != null) target.font = String(patch.font);
  if (patch.weight != null) target.weight = Number(patch.weight);
  if (patch.size != null) {
    const v = clampSize(patch.size);
    if (v != null) target.size = v;
  }
  if (patch.color != null && HEX_RE.test(patch.color)) target.color = patch.color;
  return next;
}

function updateBlock(comp, index, patch) {
  const next = structuredClone(comp);
  const strip = next.elements.find((e) => e.id === 'strip');
  if (!strip) throw new Error('composition has no photoStrip');
  if (index < 0 || index >= strip.blocks.length) throw new Error(`bad index ${index}`);
  strip.blocks[index] = { ...strip.blocks[index], ...patch };
  return next;
}

export function setBlockLabel(comp, index, value) {
  return updateBlock(comp, index, { label: String(value) });
}

export function setBlockPhoto(comp, index, photo) {
  return updateBlock(comp, index, { photo });
}
