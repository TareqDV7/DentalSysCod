// editor.js — host-agnostic Post Studio controller. Minimal P2b editing surface
// (template pick + add photos) over the structural renderer + client export +
// host adapter. Deep editing (text/drag/typography/phases) is P4; premium themes
// are P3. EN/AR via the STR map keyed off <html lang>.
import { TEMPLATES, MAX_BLOCKS, defaultComposition, serialize, deserialize, applyTheme,
         setText, setTypography, setBlockLabel, setBlockPhoto,
         addBlock, removeBlock, reorderBlock,
         setPosition, getPosition } from './composition.js';
import { renderComposition, EXPORT_PX } from './render.js';
import { rasterizeToPngBlob } from './rasterize.js';
import { THEME_OPTIONS, themePalette } from './themes.js';
import { ensureFontsLoaded } from './fonts.js';
import { buildTextInspector, buildBlockInspector, weightsFor } from './inspector.js';

const STR = {
  en: { templates: 'Template', add_photos: 'Add photos', download: 'Download',
        save: 'Save to Gallery', gallery: 'Saved posts', empty: 'No saved posts yet.',
        reopen: 'Edit', del: 'Delete', saved: 'Saved.', save_failed: 'Save failed',
        dl_failed: 'Download failed', open_failed: 'Could not open post',
        del_confirm: 'Delete this post?', theme: 'Theme',
        select_hint: 'Select an element to edit.' },
  ar: { templates: 'القالب', add_photos: 'إضافة صور', download: 'تنزيل',
        save: 'حفظ في المعرض', gallery: 'المنشورات المحفوظة', empty: 'لا توجد منشورات بعد.',
        reopen: 'تعديل', del: 'حذف', saved: 'تم الحفظ.', save_failed: 'فشل الحفظ',
        dl_failed: 'فشل التنزيل', open_failed: 'تعذر فتح المنشور',
        del_confirm: 'حذف هذا المنشور؟', theme: 'القالب اللوني',
        select_hint: 'اختر عنصرًا لتعديله.' },
};
const TPL_LABEL = {
  en: { before_after: 'Before / After', multi_phase: 'Multi-Phase',
        quad_grid: 'Quad Grid', single_feature: 'Single Feature' },
  ar: { before_after: 'قبل / بعد', multi_phase: 'متعدد المراحل',
        quad_grid: 'شبكة رباعية', single_feature: 'صورة واحدة' },
};

const PREVIEW_W = 360; // displayed width; the stage renders at native export px.

function el(tag, attrs = {}, styles = {}) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'text') node.textContent = v;
    else node.setAttribute(k, v);
  }
  Object.assign(node.style, styles);
  return node;
}

export function mountEditor(rootEl, host, opts = {}) {
  ensureFontsLoaded();
  const lang = document.documentElement.lang === 'ar' ? 'ar' : 'en';
  const s = STR[lang];
  const tl = TPL_LABEL[lang];
  const state = { comp: opts.initialComp || defaultComposition('before_after'), selectedRef: null };

  rootEl.innerHTML = '';
  const layout = el('div', {}, { display: 'flex', gap: '24px', flexWrap: 'wrap', alignItems: 'flex-start' });

  // ── Controls column ──
  const controls = el('div', {}, { flex: '1', minWidth: '240px', maxWidth: '420px',
    display: 'flex', flexDirection: 'column', gap: '16px' });

  const tplGroup = el('div', {});
  tplGroup.appendChild(el('label', { text: s.templates }, { display: 'block', marginBottom: '6px', fontWeight: '600' }));
  const tplRow = el('div', {}, { display: 'flex', flexWrap: 'wrap', gap: '8px' });
  for (const key of TEMPLATES) {
    const btn = el('button', { type: 'button', 'data-ps-template': key, text: tl[key] || key }, {});
    btn.className = 'btn';
    btn.addEventListener('click', () => { state.comp = defaultComposition(key); renderPreview(); });
    tplRow.appendChild(btn);
  }
  tplGroup.appendChild(tplRow);

  const addBtn = el('button', { type: 'button', 'data-ps-action': 'add-photos', text: s.add_photos }, {});
  addBtn.className = 'btn';
  addBtn.addEventListener('click', onAddPhotos);

  const actions = el('div', {}, { display: 'flex', gap: '8px', marginTop: '4px' });
  const saveBtn = el('button', { type: 'button', 'data-ps-action': 'save', text: s.save }, {});
  saveBtn.className = 'btn btn-primary';
  saveBtn.addEventListener('click', onSave);
  const dlBtn = el('button', { type: 'button', 'data-ps-action': 'download', text: s.download }, {});
  dlBtn.className = 'btn';
  dlBtn.addEventListener('click', onDownload);
  actions.appendChild(saveBtn);
  actions.appendChild(dlBtn);

  // ── Theme picker ──
  const themeGroup = el('div', {});
  themeGroup.appendChild(el('label', { text: s.theme }, { display: 'block', marginBottom: '6px', fontWeight: '600' }));
  const themeRow = el('div', {}, { display: 'flex', flexWrap: 'wrap', gap: '8px' });
  for (const opt of THEME_OPTIONS) {
    const b = el('button', { type: 'button', 'data-ps-theme': opt.id,
      text: lang === 'ar' ? opt.label_ar : opt.label }, {});
    b.className = 'btn';
    b.addEventListener('click', () => { state.comp = applyTheme(state.comp, opt.id); renderPreview(); });
    themeRow.appendChild(b);
  }
  themeGroup.appendChild(themeRow);

  // ── Contextual inspector slot (filled by renderInspector) ──
  const inspectorSlot = el('div', { 'data-ps-inspector': '' }, {
    display: 'flex', flexDirection: 'column', gap: '10px',
    padding: '12px', border: '1px solid rgba(0,0,0,.12)', borderRadius: '8px' });

  controls.appendChild(tplGroup);
  controls.appendChild(themeGroup);
  controls.appendChild(inspectorSlot);
  controls.appendChild(addBtn);
  controls.appendChild(actions);

  // ── Preview column ──
  const previewCol = el('div', {}, { flex: '1', minWidth: '260px', display: 'flex',
    flexDirection: 'column', alignItems: 'center', gap: '12px' });
  const previewBox = el('div', { 'data-ps-preview': '' }, { position: 'relative', overflow: 'hidden' });
  previewCol.appendChild(previewBox);

  // Map a hit element to { sel (inspector ref), pos (drag/position ref) }.
  function refsFor(node) {
    const elNode = node.closest('[data-ps-el]');
    if (elNode) {
      const v = elNode.getAttribute('data-ps-el');   // title.headline | title.subline | doctor
      return { sel: v, pos: v === 'doctor' ? 'doctor' : 'title' };
    }
    const pillNode = node.closest('[data-ps-pill-block]');
    if (pillNode) {
      const i = pillNode.getAttribute('data-ps-pill-block');
      return { sel: 'block:' + i, pos: 'pill:' + i };
    }
    const blockNode = node.closest('[data-ps-block]');
    if (blockNode) {
      const i = blockNode.getAttribute('data-ps-block');
      return { sel: 'block:' + i, pos: 'panel:' + i };
    }
    return null;
  }

  // Pointer-drag controller — selects on pointerdown, moves on pointermove.
  let drag = null;
  previewBox.addEventListener('pointerdown', (e) => {
    const refs = refsFor(e.target);
    if (!refs) { selectRef(null); return; }
    selectRef(refs.sel);
    const [W, H] = EXPORT_PX[state.comp.size] || EXPORT_PX.square;
    const scale = PREVIEW_W / W;
    drag = { posRef: refs.pos, startX: e.clientX, startY: e.clientY, scale, W, H,
             orig: getPosition(state.comp, refs.pos) };
    previewBox.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  previewBox.addEventListener('pointermove', (e) => {
    if (!drag || !drag.scale) return;
    const nx = drag.orig.x + (e.clientX - drag.startX) / drag.scale / drag.W;
    const ny = drag.orig.y + (e.clientY - drag.startY) / drag.scale / drag.H;
    state.comp = setPosition(state.comp, drag.posRef, { x: nx, y: ny });
    renderPreview();
  });
  function endDrag() { if (drag) { drag = null; renderInspector(); } }
  previewBox.addEventListener('pointerup', endDrag);
  previewBox.addEventListener('pointercancel', endDrag);

  layout.appendChild(controls);
  layout.appendChild(previewCol);

  // ── Gallery ──
  const gallery = el('div', {}, { marginTop: '24px' });
  gallery.appendChild(el('h3', { text: s.gallery }, { margin: '0 0 16px', fontSize: '1rem', fontWeight: '600' }));
  const galleryGrid = el('div', { 'data-ps-gallery': '' }, {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '16px' });
  const galleryEmpty = el('p', { text: s.empty }, { display: 'none', fontSize: '0.9em', opacity: '0.7' });
  gallery.appendChild(galleryGrid);
  gallery.appendChild(galleryEmpty);

  rootEl.appendChild(layout);
  rootEl.appendChild(gallery);

  function renderPreview() {
    const stage = renderComposition(state.comp);
    const [w, h] = EXPORT_PX[state.comp.size] || EXPORT_PX.square;
    const scale = PREVIEW_W / w;
    previewBox.innerHTML = '';
    previewBox.style.width = `${PREVIEW_W}px`;
    previewBox.style.height = `${h * scale}px`;
    const scaler = el('div', {}, { transformOrigin: 'top left', transform: `scale(${scale})` });
    scaler.appendChild(stage);
    previewBox.appendChild(scaler);
    previewBox._stage = stage; // native-size node for export
    if (state.selectedRef) {
      const sel = state.selectedRef.startsWith('block:')
        ? stage.querySelector(`[data-ps-block="${state.selectedRef.slice(6)}"]`)
        : stage.querySelector(`[data-ps-el="${state.selectedRef}"]`);
      if (sel) { sel.style.outline = '3px solid #38bdf8'; sel.style.outlineOffset = '4px'; }
    }
  }

  function selectRef(ref) {
    state.selectedRef = ref;
    renderPreview();
    renderInspector();
  }

  function currentRun(ref) {
    const title = state.comp.elements.find((e) => e.id === 'title');
    const doctor = state.comp.elements.find((e) => e.id === 'doctor');
    if (ref === 'title.headline') return title && title.headline;
    if (ref === 'title.subline') return title && title.subline;
    if (ref === 'doctor') return doctor;
    return null;
  }

  function renderInspector() {
    inspectorSlot.innerHTML = '';
    inspectorSlot.dataset.psSelected = state.selectedRef || '';
    const ref = state.selectedRef;
    if (!ref) {
      inspectorSlot.appendChild(el('p', { text: s.select_hint },
        { margin: '0', opacity: '0.7', fontSize: '0.9em' }));
      return;
    }
    if (ref.startsWith('block:')) {
      const i = Number(ref.slice(6));
      const strip = state.comp.elements.find((e) => e.id === 'strip');
      if (!strip || i < 0 || i >= strip.blocks.length) { state.selectedRef = null; inspectorSlot.dataset.psSelected = ''; return; }
      inspectorSlot.appendChild(buildBlockInspector(strip.blocks[i], strip.labelStyle, {
        lang, palette: themePalette(state.comp.theme),
        index: i, count: strip.blocks.length, maxBlocks: MAX_BLOCKS,
        onLabel: (v) => { state.comp = setBlockLabel(state.comp, i, v); renderPreview(); },
        onLabelTypography: (patch) => { state.comp = setTypography(state.comp, 'strip.label', patch); renderPreview(); },
        onLabelFont: (family) => {
          const allowed = weightsFor(family);
          const w = allowed.includes(strip.labelStyle.weight) ? strip.labelStyle.weight : allowed[0];
          state.comp = setTypography(state.comp, 'strip.label', { font: family, weight: w });
          renderPreview(); renderInspector();
        },
        onReplace: async () => {
          const picked = await host.pickPhotos();
          if (picked && picked.length) { state.comp = setBlockPhoto(state.comp, i, picked[0].dataUrl); renderPreview(); renderInspector(); }
        },
        onRemove: () => { state.comp = removeBlock(state.comp, i); selectRef(null); },
        onMoveLeft: () => { state.comp = reorderBlock(state.comp, i, i - 1); selectRef('block:' + (i - 1)); },
        onMoveRight: () => { state.comp = reorderBlock(state.comp, i, i + 1); selectRef('block:' + (i + 1)); },
        onAdd: () => { state.comp = addBlock(state.comp); renderPreview(); renderInspector(); },
      }));
      return;
    }
    const run = currentRun(ref);
    if (!run) return;
    inspectorSlot.appendChild(buildTextInspector(
      { text: run.text, font: run.font, size: run.size, weight: run.weight, color: run.color },
      {
        lang,
        palette: themePalette(state.comp.theme),
        onText: (v) => { state.comp = setText(state.comp, ref, v); renderPreview(); },
        onTypography: (patch) => { state.comp = setTypography(state.comp, ref, patch); renderPreview(); },
        onFont: (family) => {
          const allowed = weightsFor(family);
          const w = allowed.includes(run.weight) ? run.weight : allowed[0];
          state.comp = setTypography(state.comp, ref, { font: family, weight: w });
          renderPreview(); renderInspector();
        },
      }));
  }

  async function onAddPhotos() {
    const picked = await host.pickPhotos();
    if (!picked || !picked.length) return;
    const strip = state.comp.elements.find((e) => e.id === 'strip');
    if (!strip) return;
    let next = state.comp; let pi = 0;
    strip.blocks.forEach((b, i) => {
      if (!b.photo && pi < picked.length) { next = setBlockPhoto(next, i, picked[pi++].dataUrl); }
    });
    state.comp = next;
    renderPreview();
  }

  async function exportBlob() {
    // export captures the native-size stage (not the scaled preview)
    const stage = renderComposition(state.comp);
    const holder = el('div', {}, { position: 'fixed', left: '-99999px', top: '0' });
    holder.appendChild(stage);
    document.body.appendChild(holder);
    try {
      return await rasterizeToPngBlob(stage, 2);
    } finally {
      holder.remove();
    }
  }

  async function onDownload() {
    try {
      const blob = await exportBlob();
      const url = URL.createObjectURL(blob);
      const a = el('a', { href: url, download: 'post.png' }, {});
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      notify(s.dl_failed + ': ' + e.message);
    }
  }

  async function onSave() {
    try {
      const blob = await exportBlob();
      await host.savePost(blob, serialize(state.comp), {
        theme: state.comp.theme, size: state.comp.size,
        title: titleText(state.comp),
      });
      notify(s.saved);
      await refreshGallery();
    } catch (e) {
      notify(s.save_failed + ': ' + e.message);
    }
  }

  async function refreshGallery() {
    let posts = [];
    try { posts = await host.listPosts(); } catch (e) { posts = []; }
    galleryGrid.innerHTML = '';
    galleryEmpty.style.display = posts.length ? 'none' : '';
    for (const post of posts) {
      galleryGrid.appendChild(galleryCard(post));
    }
  }

  function galleryCard(post) {
    const card = el('div', { 'data-ps-gallery-item': '' }, {
      border: '1px solid rgba(0,0,0,.12)', borderRadius: '8px', padding: '10px',
      display: 'flex', flexDirection: 'column', gap: '8px' });
    card.appendChild(el('div', { text: (post.title || '') + ' · ' + (post.theme || '') },
      { fontSize: '0.82em', opacity: '0.8' }));
    const row = el('div', {}, { display: 'flex', gap: '6px' });
    const edit = el('button', { type: 'button', 'data-ps-action': 'reopen', text: s.reopen }, {});
    edit.className = 'btn';
    edit.addEventListener('click', () => reopen(post.id));
    const del = el('button', { type: 'button', 'data-ps-action': 'gdelete', text: s.del }, {});
    del.className = 'btn btn-danger';
    del.addEventListener('click', () => removePost(post.id));
    row.appendChild(edit);
    row.appendChild(del);
    card.appendChild(row);
    return card;
  }

  async function reopen(id) {
    try {
      const post = await host.getPost(id);
      if (post && post.template_json) {
        state.comp = deserialize(post.template_json);
        renderPreview();
        previewBox.scrollIntoView({ block: 'center' });
      }
    } catch (e) {
      notify(s.open_failed + ': ' + e.message);
    }
  }

  async function removePost(id) {
    if (typeof window.showConfirm === 'function') {
      const ok = await window.showConfirm({ message: s.del_confirm, danger: true });
      if (!ok) return;
    }
    await host.deletePost(id);
    await refreshGallery();
  }

  function notify(msg) {
    if (typeof window.showToast === 'function') window.showToast(msg);
  }

  // Live EN/AR re-render: re-mount in the new language, preserving the composition.
  if (rootEl._psLangObserver) { rootEl._psLangObserver.disconnect(); rootEl._psLangObserver = null; }
  const langObserver = new MutationObserver(() => {
    const cur = document.documentElement.lang === 'ar' ? 'ar' : 'en';
    if (cur !== lang) {
      langObserver.disconnect();
      rootEl._psLangObserver = null;
      mountEditor(rootEl, host, { initialComp: state.comp });
    }
  });
  langObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
  rootEl._psLangObserver = langObserver;

  // init
  renderPreview();
  renderInspector();
  refreshGallery();
  rootEl.dataset.psReady = '1';
}

function titleText(comp) {
  const t = (comp.elements || []).find((e) => e.id === 'title');
  return t && t.headline ? (t.headline.text || '') : '';
}
