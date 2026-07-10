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
  return elt('label', { text }, { fontSize: '0.8em', opacity: '0.75' });
}

// Reuses the app-wide `.form-group` styling (rounded, themed input/select/
// textarea — see templates.py) instead of bare unstyled native controls.
function fieldWrap(labelText) {
  const wrap = elt('div', { class: 'form-group' }, { marginBottom: '0' });
  wrap.appendChild(fieldLabel(labelText));
  return wrap;
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
// run.text === undefined means "typography-only" (e.g. a block label's font/
// size/weight/color, not a text run) — the Text field is skipped rather than
// shown wired to a no-op, which previously looked editable but silently
// discarded whatever was typed into it.
export function buildTextInspector(run, opts) {
  const ar = opts.lang === 'ar';
  const root = elt('div', { 'data-ps-inspector-text': '' },
    { display: 'flex', flexDirection: 'column', gap: '10px' });

  if (run.text !== undefined) {
    const text = elt('input', { type: 'text', 'data-ps-field': 'text', value: run.text || '' }, { width: '100%' });
    text.addEventListener('input', () => opts.onText(text.value));
    const textWrap = fieldWrap(ar ? 'النص' : 'Text');
    textWrap.appendChild(text);
    root.appendChild(textWrap);
  }

  const font = elt('select', { 'data-ps-field': 'font' }, { width: '100%' });
  for (const o of FONT_OPTIONS) {
    const opt = elt('option', { value: o.family, text: ar ? o.label_ar : o.label });
    if (o.family === run.font) opt.selected = true;
    font.appendChild(opt);
  }
  font.addEventListener('change', () => opts.onFont(font.value));
  const fontWrap = fieldWrap(ar ? 'الخط' : 'Font');
  fontWrap.appendChild(font);
  root.appendChild(fontWrap);

  const size = elt('input', { type: 'range', 'data-ps-field': 'size',
    min: String(SIZE_MIN), max: String(SIZE_MAX), value: String(run.size || 40) },
    { width: '100%', accentColor: 'var(--accent, #2f7ea3)' });
  size.addEventListener('input', () => {
    sizeWrap.firstChild.textContent = (ar ? 'الحجم' : 'Size') + ': ' + size.value;
    opts.onTypography({ size: Number(size.value) });
  });
  const sizeWrap = fieldWrap((ar ? 'الحجم' : 'Size') + ': ' + (run.size || 40));
  sizeWrap.appendChild(size);
  root.appendChild(sizeWrap);

  const weight = elt('select', { 'data-ps-field': 'weight' }, { width: '100%' });
  for (const w of weightsFor(run.font)) {
    const opt = elt('option', { value: String(w), text: String(w) });
    if (w === run.weight) opt.selected = true;
    weight.appendChild(opt);
  }
  weight.addEventListener('change', () => opts.onTypography({ weight: Number(weight.value) }));
  const weightWrap = fieldWrap(ar ? 'السماكة' : 'Weight');
  weightWrap.appendChild(weight);
  root.appendChild(weightWrap);

  const colorWrap = fieldWrap(ar ? 'اللون' : 'Color');
  colorWrap.appendChild(colorRow(opts.palette, run.color, (hex) => opts.onTypography({ color: hex })));
  root.appendChild(colorWrap);

  return root;
}

function actionBtn(label, action, disabled, onClick) {
  const b = elt('button', { type: 'button', 'data-ps-action': action, text: label });
  b.className = 'btn';
  if (disabled) { b.disabled = true; b.style.opacity = '0.5'; }
  else b.addEventListener('click', onClick);
  return b;
}

// block: { photo, badge, label, labelStyle, pill }
// opts: { lang, palette, index, count, maxBlocks,
//         onLabel, onLabelTypography, onLabelFont, onToggleDouble,
//         onReplace, onRemove, onMoveLeft, onMoveRight, onAdd }
export function buildBlockInspector(block, opts) {
  const ar = opts.lang === 'ar';
  const root = elt('div', { 'data-ps-inspector-block': '' },
    { display: 'flex', flexDirection: 'column', gap: '10px' });

  const label = elt('input', { type: 'text', 'data-ps-field': 'label', value: block.label || '' }, { width: '100%' });
  label.addEventListener('input', () => opts.onLabel(label.value));
  const labelWrap = fieldWrap(ar ? 'التسمية' : 'Label');
  labelWrap.appendChild(label);
  root.appendChild(labelWrap);

  const ls = block.labelStyle || {};
  root.appendChild(buildTextInspector(
    { text: undefined, font: ls.font, size: ls.size, weight: ls.weight, color: ls.color },
    { lang: opts.lang, palette: opts.palette,
      onText: () => {}, onTypography: opts.onLabelTypography, onFont: opts.onLabelFont }));

  const isDouble = !!(block.pill && block.pill.width === 'double');
  const isLast = opts.index >= opts.count - 1;
  const doubleBtn = actionBtn(
    isDouble ? (ar ? 'عرض مفرد' : 'Single width') : (ar ? 'عرض مزدوج' : 'Double width'),
    'toggle-double', isLast, opts.onToggleDouble);
  root.appendChild(doubleBtn);

  const photoRow = elt('div', {}, { display: 'flex', gap: '8px' });
  photoRow.appendChild(actionBtn(ar ? 'استبدال الصورة' : 'Replace photo', 'replace', false, opts.onReplace));
  photoRow.appendChild(actionBtn(ar ? 'حذف' : 'Remove', 'remove', opts.count <= 1, opts.onRemove));
  root.appendChild(photoRow);

  const moveRow = elt('div', {}, { display: 'flex', gap: '8px' });
  moveRow.appendChild(actionBtn('◄', 'move-left', opts.index <= 0, opts.onMoveLeft));
  moveRow.appendChild(actionBtn('►', 'move-right', opts.index >= opts.count - 1, opts.onMoveRight));
  moveRow.appendChild(actionBtn(ar ? '+ كتلة' : '+ Add block', 'add-block', opts.count >= opts.maxBlocks, opts.onAdd));
  root.appendChild(moveRow);

  return root;
}
