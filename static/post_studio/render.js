// render.js — pure structural renderer: composition -> native-size DOM stage.
// INLINE STYLES ONLY (the foreignObject export context can't reach <style>).
// Structural layout + legible defaults; premium theme tokens land in P3.

export const EXPORT_PX = {
  square: [1080, 1080],
  portrait: [1080, 1350],
  story: [1080, 1920],
};

// Neutral per-theme background placeholder (P3 replaces with the full token set).
const THEME_BG = {
  dark_premium: 'radial-gradient(60% 50% at 50% 38%, #15324e 0%, #0b1f33 55%, #060f1c 100%)',
  light_luxury: '#f6f1e7',
  clinical_premium: '#ffffff',
  bold_editorial: '#111111',
};

const px = (n) => `${n}px`;
const setStyle = (el, styles) => { Object.assign(el.style, styles); return el; };

function typoStyle(t) {
  if (!t) return {};
  return {
    color: t.color || '#ffffff',
    fontSize: px(t.size || 32),
    fontWeight: String(t.weight || 600),
    letterSpacing: px(t.letterSpacing || 0),
    lineHeight: '1.2',
    margin: '0',
  };
}

function buildTitle(el) {
  const box = document.createElement('div');
  setStyle(box, {
    position: 'absolute', left: '0', right: '0',
    top: `${(el.y ?? 0.10) * 100}%`, transform: 'translateY(-50%)',
    textAlign: el.align || 'center', padding: '0 6%', boxSizing: 'border-box',
  });
  const head = document.createElement('div');
  head.textContent = el.headline ? (el.headline.text || '') : '';
  setStyle(head, typoStyle(el.headline));
  const sub = document.createElement('div');
  sub.textContent = el.subline ? (el.subline.text || '') : '';
  setStyle(sub, typoStyle(el.subline));
  box.appendChild(head);
  box.appendChild(sub);
  return box;
}

function buildCard(b, el) {
  const card = document.createElement('div');
  setStyle(card, {
    position: 'relative', flex: '1 1 0', display: 'flex',
    flexDirection: 'column', gap: '14px', alignItems: 'center', minWidth: '0',
  });
  const frame = document.createElement('div');
  setStyle(frame, {
    position: 'relative', width: '100%', aspectRatio: '1 / 1',
    borderRadius: '28px', overflow: 'hidden',
    border: '1px solid rgba(120,200,220,.35)',
    boxShadow: '0 0 40px rgba(60,160,180,.25) inset',
    background: 'rgba(255,255,255,.05)',
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
    borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: 'rgba(0,0,0,.55)', color: '#ffffff', fontWeight: '700', fontSize: '26px',
  });
  frame.appendChild(badge);
  const label = document.createElement('div');
  label.textContent = b.label || '';
  setStyle(label, { ...typoStyle(el.labelStyle), textAlign: 'center' });
  card.appendChild(frame);
  card.appendChild(label);
  return card;
}

function buildStrip(el) {
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
  for (const b of blocks) wrap.appendChild(buildCard(b, el));
  return wrap;
}

function buildDoctor(el) {
  const box = document.createElement('div');
  box.textContent = el.text || '';
  setStyle(box, {
    position: 'absolute', left: '0', right: '0',
    top: `${(el.y ?? 0.93) * 100}%`, transform: 'translateY(-50%)',
    textAlign: el.align || 'center',
    textTransform: 'uppercase',
    color: el.color || '#c9a227',
    fontSize: px(el.size || 34),
    fontWeight: String(el.weight || 700),
    letterSpacing: px(el.letterSpacing || 4),
  });
  return box;
}

export function renderComposition(comp) {
  const [w, h] = EXPORT_PX[comp.size] || EXPORT_PX.square;
  const stage = document.createElement('div');
  stage.setAttribute('data-ps-stage', '');
  setStyle(stage, {
    position: 'relative', width: px(w), height: px(h), overflow: 'hidden',
    background: THEME_BG[comp.theme] || THEME_BG.dark_premium,
    fontFamily: 'system-ui, "Segoe UI", sans-serif',
  });
  for (const el of (comp.elements || [])) {
    if (el.type === 'title') stage.appendChild(buildTitle(el));
    else if (el.type === 'photoStrip') stage.appendChild(buildStrip(el));
    else if (el.type === 'doctorName') stage.appendChild(buildDoctor(el));
  }
  return stage;
}
