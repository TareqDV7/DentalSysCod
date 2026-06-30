// inspector.js — pure DOM builders for the Post Studio selection inspector.
// No serialization touches this; it builds editor-chrome controls only.
import { FONT_OPTIONS } from './fonts.js';
import { SIZE_MIN, SIZE_MAX } from './composition.js';

export const WEIGHTS_BY_FAMILY = {
  'Manrope': [400, 700, 800],
  'Playfair Display': [700],
  'Cairo': [400, 700],
  'Poppins': [400, 700],
};

export function weightsFor(family) {
  return WEIGHTS_BY_FAMILY[family] || [400, 700];
}

function elt(tag, attrs = {}, styles = {}) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'text') n.textContent = v; else n.setAttribute(k, v);
  }
  Object.assign(n.style, styles);
  return n;
}

function fieldLabel(text) {
  return elt('label', { text }, { display: 'block', fontSize: '0.8em', opacity: '0.75', marginBottom: '2px' });
}

function colorRow(palette, current, onColor) {
  const row = elt('div', {}, { display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' });
  for (const hex of palette) {
    const sw = elt('button', { type: 'button', 'data-ps-swatch': hex }, {
      width: '22px', height: '22px', borderRadius: '50%', cursor: 'pointer',
      background: hex, border: hex.toUpperCase() === String(current).toUpperCase()
        ? '2px solid #38bdf8' : '1px solid rgba(0,0,0,.25)' });
    sw.addEventListener('click', () => onColor(hex));
    row.appendChild(sw);
  }
  const custom = elt('input', { type: 'text', 'data-ps-field': 'color', placeholder: '#______',
    value: current || '' }, { width: '92px', marginInlineStart: '4px' });
  custom.addEventListener('input', () => onColor(custom.value));
  row.appendChild(custom);
  return row;
}

// run: { text, font, size, weight, color }
// opts: { lang, palette, onText, onTypography, onFont }
export function buildTextInspector(run, opts) {
  const ar = opts.lang === 'ar';
  const root = elt('div', { 'data-ps-inspector-text': '' },
    { display: 'flex', flexDirection: 'column', gap: '10px' });

  const text = elt('input', { type: 'text', 'data-ps-field': 'text', value: run.text || '' }, { width: '100%' });
  text.addEventListener('input', () => opts.onText(text.value));
  const textWrap = elt('div'); textWrap.appendChild(fieldLabel(ar ? 'النص' : 'Text')); textWrap.appendChild(text);
  root.appendChild(textWrap);

  const font = elt('select', { 'data-ps-field': 'font' }, { width: '100%' });
  for (const o of FONT_OPTIONS) {
    const opt = elt('option', { value: o.family, text: ar ? o.label_ar : o.label });
    if (o.family === run.font) opt.selected = true;
    font.appendChild(opt);
  }
  font.addEventListener('change', () => opts.onFont(font.value));
  const fontWrap = elt('div'); fontWrap.appendChild(fieldLabel(ar ? 'الخط' : 'Font')); fontWrap.appendChild(font);
  root.appendChild(fontWrap);

  const size = elt('input', { type: 'range', 'data-ps-field': 'size',
    min: String(SIZE_MIN), max: String(SIZE_MAX), value: String(run.size || 40) }, { width: '100%' });
  size.addEventListener('input', () => opts.onTypography({ size: Number(size.value) }));
  const sizeWrap = elt('div');
  sizeWrap.appendChild(fieldLabel((ar ? 'الحجم' : 'Size') + ': ' + (run.size || 40)));
  sizeWrap.appendChild(size);
  root.appendChild(sizeWrap);

  const weight = elt('select', { 'data-ps-field': 'weight' }, { width: '100%' });
  for (const w of weightsFor(run.font)) {
    const opt = elt('option', { value: String(w), text: String(w) });
    if (w === run.weight) opt.selected = true;
    weight.appendChild(opt);
  }
  weight.addEventListener('change', () => opts.onTypography({ weight: Number(weight.value) }));
  const weightWrap = elt('div'); weightWrap.appendChild(fieldLabel(ar ? 'السماكة' : 'Weight')); weightWrap.appendChild(weight);
  root.appendChild(weightWrap);

  const colorWrap = elt('div'); colorWrap.appendChild(fieldLabel(ar ? 'اللون' : 'Color'));
  colorWrap.appendChild(colorRow(opts.palette, run.color, (hex) => opts.onTypography({ color: hex })));
  root.appendChild(colorWrap);

  return root;
}
