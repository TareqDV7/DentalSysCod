# Post Studio Redesign — Phase 2b (Editor Core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the working client-side Post Studio editor on top of the P2a foundations — a host-agnostic ESM bundle that renders a composition to a live DOM canvas, exports it to PNG client-side, and creates/saves/reopens/deletes posts through a host adapter — and mount it in the (currently inert) desktop tab.

**Architecture:** P2a delivered the non-UI foundations: the `template_json` schema, the pure `composition.js` state model (node-tested), the reworked Flask endpoints (`POST /api/posts/photos`, `POST /api/posts` save-PNG+spec, `GET /api/posts/<id>` spec, dir-aware delete), and a validated rasterization technique (spike decision = **PASS**, SVG `<foreignObject>` → canvas). **P2b (this plan)** builds the browser side: a small set of co-located ESM modules — `render.js` (composition → DOM canvas), `rasterize.js` (the hardened spike rasterizer → PNG `Blob`), `host.js` (the `PostStudioHost` adapter + a desktop host over `fetch`), and `editor.js` (the controller) — served same-origin by a frozen-safe Flask route and mounted into the Post Studio tab. The premium 4-theme styling + bundled fonts land in **P3**; deep customization (drag-position, snap guides, the full per-element typography inspector, the phase add/reorder/insert UI, editable title/subline text) lands in **P4**. P2b's renderer is therefore deliberately *structural* (legible, exportable, round-trips), not premium-styled, and its editing surface is the minimal set needed for a real create → preview → export → save → reopen loop (template choice + photo add).

**Tech Stack:** Flask (`dental_clinic.py`), pure ESM JavaScript (no bundler, no new runtime deps), Chromium (WebView2 desktop / Android System WebView mobile), `node --test` (Node's built-in runner) for the DOM-free module, Playwright for the DOM/visual checks. The modules use **relative** imports (`./composition.js`) so the identical files load both same-origin on desktop and as Flutter assets under `file://` in P6.

## Global Constraints

- **No CDN / no remote assets at runtime** — everything served same-origin or bundled (project rule). Vendoring is allowed; runtime CDN fetches are not. The editor ESM is served same-origin via a Flask route and bundled into the frozen exe.
- **EN/AR throughout, RTL-aware** — every user-facing string has an `en` and `ar` form. The editor module carries its own small bilingual string map (`STR`), keyed off `document.documentElement.lang` (`'ar'` → Arabic, else English); it does **not** depend on the inline-template `t()`.
- **Immutability** — the editor mutates a single local `state.comp` by replacing it with new compositions from `composition.js` helpers (which never mutate inputs). The renderer treats its input as read-only.
- **Inline styles only in `render.js`** — the SVG `<foreignObject>` render context has no access to external/`<style>` stylesheets, so every visual property the export must capture is set as an **inline** style on the node (this is why the P2a spike worked, and the spike note records it). Do not move render styling into CSS classes.
- **`web_assets.py` cannot be opened by the Read/Edit tools** (~249k tokens of inlined base64). P2b does **not** touch it.
- **`HTML_TEMPLATE` is a normal Python string** rendered with `render_template_string` (Jinja). Inside inline `<script>`, a JS `'\n'` must be written `'\\n'` (a real newline breaks the script). P2b adds **one** small inline `<script type="module">` (the mount entry) plus an HTML mount point, and removes the leftover P2a gallery JS — keep the escaping rule in mind for the entry script.
- **Frozen-resource root:** `_BUNDLE_DIR = Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).parent` (already in `dental_clinic.py:213`). The module-serving route resolves files under `_BUNDLE_DIR / 'static' / 'post_studio'`, and `static/` is added to `DentaCare.spec` datas so the frozen exe ships it. (No interim release; the exe rebuild is a later user-side step, but the route + spec must be correct now.)
- **CSRF is automatic:** the portal page installs a `window.fetch` interceptor (`templates.py:3347`) that adds `X-CSRFToken` to same-origin unsafe methods. The desktop host uses plain `fetch`; no manual token handling.
- **Commits:** conventional-commit messages, no attribution footer (repo setting).
- **Gate:** `python -m pytest tests/` exits `0` (summary suppressed — check the exit code) **and** `node --test tests/js/` exits `0`. Playwright checks are `importorskip`-guarded (skip cleanly if Playwright is absent in-env); when present they must pass.

## File Structure (decomposition locked here)

- **Create** `static/post_studio/render.js` — pure structural renderer. `renderComposition(comp) → HTMLElement` (a native-export-size stage node with inline-styled children per element type) + `EXPORT_PX`. DOM-dependent (uses `document`); validated via Playwright, not node.
- **Create** `static/post_studio/rasterize.js` — `rasterizeToPngBlob(node, scale=2) → Promise<Blob>`, the hardened spike rasterizer (foreignObject → Image → canvas → `toBlob`), `await document.fonts.ready`. Validated via Playwright.
- **Create** `static/post_studio/host.js` — the `PostStudioHost` typedef + `createDesktopHost() → host` (`pickPhotos` via a hidden file input; `savePost`/`listPosts`/`getPost`/`deletePost` via `fetch`). The DOM-free shape (the returned object’s method set) is node-testable; the DOM/network bodies are covered by the editor Playwright harness + the P2a endpoint tests.
- **Create** `static/post_studio/editor.js` — `mountEditor(rootEl, host) → void`, the controller: template picker, add-photos, live scaled preview, Download, Save, and the saved-posts gallery (reopen-to-edit / delete). Consumes `composition.js`, `render.js`, `rasterize.js`. Carries the EN/AR `STR` map.
- **Create** `static/post_studio/spike/render_harness.html` + `static/post_studio/spike/editor_harness.html` — self-contained Playwright harnesses (loaded via `file://`, relative module imports), kept in-repo as living proof.
- **Create** `tests/js/host.test.mjs` — node shape test for `createDesktopHost()`.
- **Create** `tests/e2e/test_editor_render.py` — Playwright: `render.js` produces the expected DOM per template, and `rasterize.js` yields a correctly-sized, non-blank, untainted PNG.
- **Create** `tests/e2e/test_editor_flow.py` — Playwright: `editor.js` against a fake in-memory host — template select, add photos, save (host called), reopen (re-render). No server.
- **Create** `tests/e2e/test_post_studio_smoke.py` — Playwright full-portal smoke (login → open tab → pick template → add photo → preview → save → gallery → reopen), `importorskip`-guarded; documents the manual fallback.
- **Modify** `dental_clinic.py` — add `GET /post_studio/<path:filename>` (frozen-safe static-asset route) and open it in the before-request gate.
- **Modify** `DentaCare.spec` — add `('static', 'static')` to the shared datas.
- **Modify** `templates.py` — replace the inert P2a placeholder with `<div id="ps-editor-root">`; remove the leftover P2a gallery section (`#psGallery`/`#psGalleryEmpty`) and the slim `psLoadGallery`/`psOnTabOpen` inline JS (superseded by the module); add the inline `<script type="module">` mount entry; point the tab-open dispatcher at it.
- **Modify** `tests/test_post_studio_ui.py` — update the gallery/JS-presence assertions to the new mount-root + module-entry shape; keep the tab-shell + icon + branding tests.

## Phase roadmap (context)

This plan covers **P2b only**. Spec: `docs/superpowers/specs/2026-06-27-post-studio-redesign.md`. P1 (cleanups) and P2a (foundations) are DONE. After P2b: **P3** premium themes + starter-template styling + bundled fonts; **P4** deep customization (drag/snap/inspector/phase-edit/editable title); **P5** desktop QA; **P6** mobile editor parity (the Flutter WebView host reuses these exact modules as assets). PR strategy unchanged: HOLD the PR, stack P2b–P6 on `feat/post-studio`, ONE PR once the editor fully replaces Pillow.

**Interim state at end of P2b (expected, acceptable):** the Post Studio tab works end-to-end — pick a starter template, add photos, see a live preview, Download or Save to the gallery, reopen a saved post to continue. Styling is structural (one neutral per-theme background placeholder), and text/drag/phase editing is not yet exposed (P3/P4). No interim release.

---

### Task 1: Frozen-safe module-serving route + bundle packaging

The editor ESM must load same-origin on desktop (dev **and** frozen exe). `app = Flask(__name__)` would serve `static/` via `/static`, but Flask's static path is unreliable under PyInstaller, and the project bundles resources via `_BUNDLE_DIR`. Add a small explicit route that serves `static/post_studio/<file>` from `_BUNDLE_DIR` with the correct JS mimetype and no path traversal, and bundle `static/` in the spec.

**Files:**
- Modify: `dental_clinic.py` (add the route near the other `/api/posts` routes; open it in the before-request gate at `dental_clinic.py:2060-2066`)
- Modify: `DentaCare.spec` (add `('static', 'static')` to `COMMON_DATAS`)
- Test: `tests/test_post_studio_api.py`

**Interfaces:**
- Consumes: `_BUNDLE_DIR` (`dental_clinic.py:213`), `send_file`, `Path`.
- Produces: `GET /post_studio/<path:filename>` → the file under `static/post_studio/` with `text/javascript` for `.js`, `application/json` for `.json`; `404` for missing; `403`/`404` for traversal attempts. Reachable without a session (it is a public asset, like static files).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_post_studio_api.py`:

```python
def test_post_studio_module_served(client):
    # composition.js (created in P2a) must be served same-origin with a JS mimetype.
    r = client.get('/post_studio/composition.js')
    assert r.status_code == 200
    assert r.content_type.startswith('text/javascript') or 'javascript' in r.content_type
    assert b'defaultComposition' in r.data


def test_post_studio_module_served_without_login(client):
    # It is a public asset (the logged-in portal page references it, but the
    # asset route itself must not require the portal session).
    r = client.get('/post_studio/composition.js')
    assert r.status_code == 200


def test_post_studio_module_missing_is_404(client):
    assert client.get('/post_studio/does-not-exist.js').status_code == 404


def test_post_studio_module_rejects_traversal(client):
    # Must not escape static/post_studio/.
    r = client.get('/post_studio/..%2f..%2fdental_clinic.py')
    assert r.status_code in (403, 404)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_post_studio_api.py -k module -v`
Expected: FAIL — route does not exist (404 for the served-file tests).

- [ ] **Step 3: Add the route + open it in the gate**

In `dental_clinic.py`, add near the other posts routes (e.g. just before `posts_photos`):

```python
_POST_STUDIO_DIR = (_BUNDLE_DIR / 'static' / 'post_studio').resolve()
_POST_STUDIO_MIME = {'.js': 'text/javascript', '.mjs': 'text/javascript',
                     '.json': 'application/json', '.css': 'text/css'}


@app.route('/post_studio/<path:filename>')
def post_studio_asset(filename):
    target = (_POST_STUDIO_DIR / filename).resolve()
    # Path-traversal guard: the resolved target must stay inside the dir.
    if _POST_STUDIO_DIR not in target.parents or not target.is_file():
        return jsonify({'error': 'Not found'}), 404
    mimetype = _POST_STUDIO_MIME.get(target.suffix.lower(), 'application/octet-stream')
    return send_file(str(target), mimetype=mimetype)
```

Then open the route in the before-request gate. In `dental_clinic.py:2060-2066`, just before the read-only `/api/posts` allowance, add:

```python
    # Editor ESM bundle is a public same-origin asset (served to the portal page).
    if request.method == 'GET' and path.startswith('/post_studio/'):
        return None
```

- [ ] **Step 4: Add `static/` to the frozen bundle**

In `DentaCare.spec`, add to `COMMON_DATAS` (next to the `('fonts', 'fonts')` entry):

```python
    # Post Studio client-side editor ESM bundle (served by /post_studio/<file>).
    ('static', 'static'),
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/test_post_studio_api.py -k module -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py DentaCare.spec tests/test_post_studio_api.py
git commit -m "feat(post-studio): frozen-safe /post_studio/<file> module route + bundle static/"
```

---

### Task 2: `rasterize.js` — client-side PNG export (vendored from the spike, hardened)

Turn the spike's proven technique into a reusable export function returning a PNG `Blob` (what `savePost` uploads). Validate it with a Playwright harness that loads it via `file://` against a hard composition node.

**Files:**
- Create: `static/post_studio/rasterize.js`
- Create: `static/post_studio/spike/render_harness.html` (shared by Tasks 2 & 3)
- Create: `tests/e2e/test_editor_render.py` (the rasterize assertions; render assertions added in Task 3)

**Interfaces:**
- Consumes: a DOM node with **inline** styles (Task 3's `renderComposition` output, or the harness's fixture node), `document.fonts`.
- Produces: `export async function rasterizeToPngBlob(node, scale = 2) → Promise<Blob>`. Throws on a tainted canvas / failed `toBlob`.

- [ ] **Step 1: Write `rasterize.js`**

Create `static/post_studio/rasterize.js`:

```javascript
// rasterize.js — client-side PNG export via SVG <foreignObject> -> canvas.
// Technique validated by the P2a spike (decision: PASS — see
// docs/superpowers/notes/2026-06-27-rasterizer-spike-decision.md). The node's
// visual styles MUST be inline (the SVG render context cannot reach external
// stylesheets), which render.js guarantees.

export async function rasterizeToPngBlob(node, scale = 2) {
  if (document.fonts && document.fonts.ready) {
    await document.fonts.ready;
  }
  const rect = node.getBoundingClientRect();
  const w = Math.round(node.offsetWidth || rect.width);
  const h = Math.round(node.offsetHeight || rect.height);
  const xhtml = new XMLSerializer().serializeToString(node);
  const svg =
    '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '">' +
      '<foreignObject x="0" y="0" width="100%" height="100%">' +
        '<div xmlns="http://www.w3.org/1999/xhtml">' + xhtml + '</div>' +
      '</foreignObject>' +
    '</svg>';
  const svgUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = () => reject(new Error('SVG render failed'));
    img.src = svgUrl;
  });
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  const ctx = canvas.getContext('2d');
  ctx.scale(scale, scale);
  ctx.drawImage(img, 0, 0);
  return await new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      // A tainted canvas yields a null blob (or throws SecurityError above).
      if (blob) resolve(blob);
      else reject(new Error('Canvas export blocked (tainted or empty)'));
    }, 'image/png');
  });
}
```

- [ ] **Step 2: Write the shared harness**

Create `static/post_studio/spike/render_harness.html`. It imports the real modules via relative paths and exposes test hooks. (Task 3 adds the `render.js` fixture wiring; this step wires the rasterize hook around a simple inline node so Task 2 is independently testable.)

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Post Studio render + rasterize harness</title>
</head>
<body>
<div id="mount"></div>
<script type="module">
  import { renderComposition } from '../render.js';
  import { rasterizeToPngBlob } from '../rasterize.js';

  // Build a composition node on demand (Task 3 exercises renderComposition;
  // Task 2 needs any inline-styled node — renderComposition supplies one).
  window.__buildStage = function (comp) {
    const mount = document.getElementById('mount');
    mount.innerHTML = '';
    const stage = renderComposition(comp);
    mount.appendChild(stage);
    window.__stage = stage;
    return stage.outerHTML.length;
  };

  window.__rasterizeError = null;
  window.__rasterize = async function () {
    try {
      const blob = await rasterizeToPngBlob(window.__stage, 2);
      const buf = await blob.arrayBuffer();
      const bytes = new Uint8Array(buf);
      // return a base64 data URL the Python side can decode
      let bin = '';
      for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      return 'data:image/png;base64,' + btoa(bin);
    } catch (e) {
      window.__rasterizeError = String(e);
      throw e;
    }
  };
</script>
</body>
</html>
```

- [ ] **Step 3: Write the failing Playwright check**

Create `tests/e2e/test_editor_render.py`:

```python
import base64
import struct
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api",
                    reason="Playwright not installed in this environment")
from playwright.sync_api import sync_playwright  # noqa: E402

HARNESS = (Path(__file__).resolve().parents[1].parent
           / "static" / "post_studio" / "spike" / "render_harness.html")

_DATA_PNG = ("data:image/png;base64,"
             "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEUlEQVR4nGNk"
             "YPjPgAcw4pMEAB0EAv9G2k0xAAAAAElFTkSuQmCC")

_COMP = {
    "version": 1, "size": "square", "theme": "dark_premium",
    "elements": [
        {"id": "title", "type": "title", "x": 0.5, "y": 0.10, "align": "center",
         "headline": {"text": "Root Canal Treatment", "size": 64, "weight": 800,
                      "color": "#ffffff", "letterSpacing": 1},
         "subline": {"text": "for Lower Molar", "size": 40, "weight": 500,
                     "color": "#5fd3c8", "letterSpacing": 0}},
        {"id": "strip", "type": "photoStrip", "layout": "row",
         "blocks": [{"photo": _DATA_PNG, "badge": 1, "label": "Before Treatment"},
                    {"photo": _DATA_PNG, "badge": 2, "label": "After Treatment"}],
         "labelStyle": {"size": 28, "weight": 600, "color": "#cfd8e3"}},
        {"id": "doctor", "type": "doctorName", "x": 0.5, "y": 0.93, "align": "center",
         "text": "DR. WASFY BARZAQ", "size": 34, "weight": 700,
         "color": "#c9a227", "letterSpacing": 4},
    ],
}


def _png_size(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return struct.unpack(">II", data[16:24])


def test_rasterize_exports_untainted_png():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2)
        page.goto(HARNESS.as_uri())
        page.evaluate("(c) => window.__buildStage(c)", _COMP)
        data_url = page.evaluate("() => window.__rasterize()")
        err = page.evaluate("() => window.__rasterizeError")
        browser.close()
    assert err is None, f"rasterizer threw: {err}"
    assert data_url.startswith("data:image/png;base64,")
    raw = base64.b64decode(data_url.split(",", 1)[1])
    w, h = _png_size(raw)
    assert (w, h) == (2160, 2160), (w, h)   # 1080 logical * scale 2
    assert len(raw) > 20_000, f"suspiciously small PNG: {len(raw)} bytes"
```

- [ ] **Step 4: Run to verify it passes (or skips cleanly)**

Run: `python -m pytest tests/e2e/test_editor_render.py::test_rasterize_exports_untainted_png -v`
Expected: PASS if Playwright is installed; SKIP otherwise. (Manual fallback: open `render_harness.html` in WebView2, run `await window.__buildStage(<comp>); await window.__rasterize()` in the console — confirm a `data:image/png` string with no `SecurityError`.)

> This step depends on `render.js` (Task 3). If executing strictly in order, write a temporary inline node in the harness for this task and replace it with `renderComposition` in Task 3 — OR execute Tasks 2 and 3 together and run this test once after Task 3. Recommended: implement `render.js` (Task 3 Step 1) before running this test.

- [ ] **Step 5: Commit**

```bash
git add static/post_studio/rasterize.js static/post_studio/spike/render_harness.html tests/e2e/test_editor_render.py
git commit -m "feat(post-studio): rasterize.js — client PNG export (vendored from spike)"
```

---

### Task 3: `render.js` — structural composition → DOM canvas

A pure renderer that turns a composition into a native-export-size DOM node with **inline** styles, so preview == export. Structural only: one neutral per-theme background placeholder; the premium token system (gradients, card/badge styling, accents) is P3.

**Files:**
- Create: `static/post_studio/render.js`
- Modify: `static/post_studio/spike/render_harness.html` (already imports it — exposes a DOM-assertion hook)
- Modify: `tests/e2e/test_editor_render.py` (add structural-DOM assertions)

**Interfaces:**
- Consumes: `composition.js` shapes (`comp.size`, `comp.theme`, `comp.elements` with `title`/`photoStrip`/`doctorName`). Importing `composition.js` is optional here (render reads the shapes directly); keep an `import` only if a constant is used, to avoid an unused import.
- Produces:
  - `export const EXPORT_PX = { square:[1080,1080], portrait:[1080,1350], story:[1080,1920] }`
  - `export function renderComposition(comp) → HTMLElement` — a `div[data-ps-stage]` sized to `EXPORT_PX[comp.size]`, containing one positioned, inline-styled child per element. Photo blocks render a rounded frame + `<img>` (the block's `photo` data-URL) + a circular numbered badge + a label; layout is a flex row, or a 2-column grid when `layout==='grid'` or `blocks.length>3`.

- [ ] **Step 1: Write `render.js`**

Create `static/post_studio/render.js`:

```javascript
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
```

- [ ] **Step 2: Add the DOM-assertion hook to the harness**

Edit `static/post_studio/spike/render_harness.html` — extend the module script with a structural query hook (append inside the existing `<script type="module">`, before the closing `</script>`):

```javascript
  window.__describe = function (comp) {
    const stage = window.__buildStage(comp) && window.__stage;
    return {
      size: [stage.offsetWidth, stage.offsetHeight],
      titles: stage.querySelectorAll('[data-ps-stage] > div')[0]
        ? stage.children[0].textContent : '',
      imgs: stage.querySelectorAll('img').length,
      badges: Array.from(stage.querySelectorAll('div'))
        .filter((d) => /^[0-9]+$/.test(d.textContent.trim()) && d.style.borderRadius === '50%')
        .map((d) => d.textContent.trim()),
      hasDoctor: stage.textContent.includes('DR.'),
    };
  };
```

- [ ] **Step 3: Add the failing structural assertions**

Append to `tests/e2e/test_editor_render.py`:

```python
def test_render_structure_before_after():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        info = page.evaluate("(c) => window.__describe(c)", _COMP)
        browser.close()
    assert info["size"] == [1080, 1080]
    assert info["imgs"] == 2                       # two photo blocks rendered
    assert info["badges"] == ["1", "2"]            # numbered badges in order
    assert info["hasDoctor"] is True


def test_render_story_size():
    comp = dict(_COMP, size="story")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        info = page.evaluate("(c) => window.__describe(c)", comp)
        browser.close()
    assert info["size"] == [1080, 1920]
```

- [ ] **Step 4: Run to verify it passes (or skips)**

Run: `python -m pytest tests/e2e/test_editor_render.py -v`
Expected: PASS (all three: rasterize + two structural) if Playwright is present; SKIP otherwise.

- [ ] **Step 5: Commit**

```bash
git add static/post_studio/render.js static/post_studio/spike/render_harness.html tests/e2e/test_editor_render.py
git commit -m "feat(post-studio): render.js — structural composition -> DOM canvas"
```

---

### Task 4: `host.js` — the host adapter + desktop host

Define the `PostStudioHost` contract and implement the desktop host over `fetch` (CSRF auto) and a hidden file input. The mobile host (P6) implements the same shape over a Dart↔JS bridge.

**Files:**
- Create: `static/post_studio/host.js`
- Create: `tests/js/host.test.mjs`

**Interfaces:**
- Consumes: `fetch`, `FileReader`, `document` (only inside method bodies, so the module imports cleanly under node).
- Produces: `export function createDesktopHost() → host` where `host` has `pickPhotos`, `savePost`, `listPosts`, `getPost`, `deletePost` (the `PostStudioHost` shape). `savePost(png, templateJson, meta)` POSTs multipart `{image, template_json, theme, size, title}` to `/api/posts` and returns the parsed `{success, id}`.

- [ ] **Step 1: Write the failing node shape test**

Create `tests/js/host.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createDesktopHost } from '../../static/post_studio/host.js';

test('createDesktopHost exposes the PostStudioHost shape', () => {
  const host = createDesktopHost();
  for (const m of ['pickPhotos', 'savePost', 'listPosts', 'getPost', 'deletePost']) {
    assert.equal(typeof host[m], 'function', `missing host.${m}`);
  }
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/host.test.mjs`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write `host.js`**

Create `static/post_studio/host.js`:

```javascript
// host.js — host adapter. The desktop host talks to Flask via fetch; the page's
// CSRF interceptor (templates.py) adds X-CSRFToken to same-origin unsafe methods,
// so no manual token handling. The mobile host (P6) implements the same shape
// over a Dart<->JS bridge. DOM/network are only touched inside method bodies, so
// this module imports cleanly under `node --test`.

/**
 * @typedef {Object} PostStudioHost
 * @property {() => Promise<{id:string, dataUrl:string}[]>} pickPhotos
 * @property {(png:Blob, templateJson:string, meta:{theme?:string,size?:string,title?:string}) => Promise<{id:number}>} savePost
 * @property {() => Promise<Object[]>} listPosts
 * @property {(id:number) => Promise<Object>} getPost
 * @property {(id:number) => Promise<void>} deletePost
 */

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = () => reject(new Error('read failed'));
    fr.readAsDataURL(file);
  });
}

/** @returns {PostStudioHost} */
export function createDesktopHost() {
  function pickPhotos() {
    return new Promise((resolve) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      input.multiple = true;
      input.style.display = 'none';
      document.body.appendChild(input);
      input.addEventListener('change', async () => {
        const files = Array.from(input.files || []);
        const out = [];
        for (const f of files) {
          out.push({ id: `${f.name}:${f.size}`, dataUrl: await fileToDataUrl(f) });
        }
        input.remove();
        resolve(out);
      }, { once: true });
      input.click();
    });
  }

  async function savePost(png, templateJson, meta) {
    const fd = new FormData();
    fd.append('image', png, 'export.png');
    fd.append('template_json', templateJson);
    fd.append('theme', (meta && meta.theme) || '');
    fd.append('size', (meta && meta.size) || '');
    fd.append('title', (meta && meta.title) || '');
    const r = await fetch('/api/posts', { method: 'POST', body: fd });
    if (!r.ok) throw new Error(`save failed: ${r.status}`);
    return await r.json();
  }

  async function listPosts() {
    const r = await fetch('/api/posts');
    if (!r.ok) throw new Error(`list failed: ${r.status}`);
    return await r.json();
  }

  async function getPost(id) {
    const r = await fetch(`/api/posts/${id}`);
    if (!r.ok) throw new Error(`get failed: ${r.status}`);
    return await r.json();
  }

  async function deletePost(id) {
    const r = await fetch(`/api/posts/${id}`, { method: 'DELETE' });
    if (!r.ok) throw new Error(`delete failed: ${r.status}`);
  }

  return { pickPhotos, savePost, listPosts, getPost, deletePost };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `node --test tests/js/host.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add static/post_studio/host.js tests/js/host.test.mjs
git commit -m "feat(post-studio): host.js — PostStudioHost adapter + desktop host"
```

---

### Task 5: `editor.js` — the controller (mount, template pick, add photos, export, save, gallery)

The host-agnostic controller that ties it together. Minimal-but-complete editing surface for P2b: choose a starter template, add photos (filling empty blocks in order), live scaled preview, Download, Save, and a saved-posts gallery with reopen-to-edit / delete. Text/drag/phase editing is P4.

**Files:**
- Create: `static/post_studio/editor.js`
- Create: `static/post_studio/spike/editor_harness.html`
- Create: `tests/e2e/test_editor_flow.py`

**Interfaces:**
- Consumes: `composition.js` (`TEMPLATES`, `defaultComposition`, `serialize`, `deserialize`), `render.js` (`renderComposition`, `EXPORT_PX`), `rasterize.js` (`rasterizeToPngBlob`), and a `PostStudioHost` (Task 4).
- Produces: `export function mountEditor(rootEl, host) → void`. Renders the editor UI into `rootEl`. For tests, it sets `rootEl.dataset.psReady = '1'` once mounted and exposes nothing global (the harness drives it via DOM + a fake host).

- [ ] **Step 1: Write the failing Playwright flow test**

Create `static/post_studio/spike/editor_harness.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Post Studio editor harness</title></head>
<body>
<div id="root"></div>
<script type="module">
  import { mountEditor } from '../editor.js';

  const TINY = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEUlEQVR4nGNkYPjPgAcw4pMEAB0EAv9G2k0xAAAAAElFTkSuQmCC";
  const saved = [];
  // Fake in-memory host (no server, no OS file dialog).
  const fakeHost = {
    async pickPhotos() { return [{ id: 'a', dataUrl: TINY }, { id: 'b', dataUrl: TINY }]; },
    async savePost(png, templateJson) {
      const id = saved.length + 1;
      saved.push({ id, title: 'T', theme: 'dark_premium', size: 'square',
                   template_json: templateJson, created_at: '2026-06-28' });
      window.__savedCount = saved.length;
      window.__lastPng = png && png.size > 0;
      return { success: true, id };
    },
    async listPosts() { return saved.slice().reverse(); },
    async getPost(id) { return saved.find((p) => p.id === id); },
    async deletePost(id) { const i = saved.findIndex((p) => p.id === id); if (i >= 0) saved.splice(i, 1); },
  };
  mountEditor(document.getElementById('root'), fakeHost);
  window.__ready = true;
</script>
</body>
</html>
```

Create `tests/e2e/test_editor_flow.py`:

```python
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api",
                    reason="Playwright not installed in this environment")
from playwright.sync_api import sync_playwright  # noqa: E402

HARNESS = (Path(__file__).resolve().parents[1].parent
           / "static" / "post_studio" / "spike" / "editor_harness.html")


def test_editor_template_addphotos_save_reopen():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(HARNESS.as_uri())
        page.wait_for_function("() => window.__ready === true")
        # mounts with a default template -> a preview stage exists
        page.wait_for_selector("[data-ps-stage]")
        # add photos via the (fake) host -> two <img> appear in the preview
        page.click("[data-ps-action='add-photos']")
        page.wait_for_function("() => document.querySelectorAll('[data-ps-stage] img').length === 2")
        # save -> fake host records the post + a non-empty PNG blob
        page.click("[data-ps-action='save']")
        page.wait_for_function("() => window.__savedCount === 1")
        assert page.evaluate("() => window.__lastPng") is True
        # gallery shows the saved post; reopen re-renders a stage
        page.wait_for_selector("[data-ps-gallery-item]")
        page.click("[data-ps-action='reopen']")
        page.wait_for_selector("[data-ps-stage]")
        browser.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/e2e/test_editor_flow.py -v`
Expected: FAIL (module `editor.js` missing) if Playwright present; SKIP otherwise.

- [ ] **Step 3: Write `editor.js`**

Create `static/post_studio/editor.js`:

```javascript
// editor.js — host-agnostic Post Studio controller. Minimal P2b editing surface
// (template pick + add photos) over the structural renderer + client export +
// host adapter. Deep editing (text/drag/typography/phases) is P4; premium themes
// are P3. EN/AR via the STR map keyed off <html lang>.
import { TEMPLATES, defaultComposition, serialize, deserialize } from './composition.js';
import { renderComposition, EXPORT_PX } from './render.js';
import { rasterizeToPngBlob } from './rasterize.js';

const STR = {
  en: { templates: 'Template', add_photos: 'Add photos', download: 'Download',
        save: 'Save to Gallery', gallery: 'Saved posts', empty: 'No saved posts yet.',
        reopen: 'Edit', del: 'Delete', saved: 'Saved.', save_failed: 'Save failed',
        del_confirm: 'Delete this post?' },
  ar: { templates: 'القالب', add_photos: 'إضافة صور', download: 'تنزيل',
        save: 'حفظ في المعرض', gallery: 'المنشورات المحفوظة', empty: 'لا توجد منشورات بعد.',
        reopen: 'تعديل', del: 'حذف', saved: 'تم الحفظ.', save_failed: 'فشل الحفظ',
        del_confirm: 'حذف هذا المنشور؟' },
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

export function mountEditor(rootEl, host) {
  const lang = document.documentElement.lang === 'ar' ? 'ar' : 'en';
  const s = STR[lang];
  const tl = TPL_LABEL[lang];
  const state = { comp: defaultComposition('before_after') };

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

  controls.appendChild(tplGroup);
  controls.appendChild(addBtn);
  controls.appendChild(actions);

  // ── Preview column ──
  const previewCol = el('div', {}, { flex: '1', minWidth: '260px', display: 'flex',
    flexDirection: 'column', alignItems: 'center', gap: '12px' });
  const previewBox = el('div', { 'data-ps-preview': '' }, { position: 'relative', overflow: 'hidden' });
  previewCol.appendChild(previewBox);

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
  }

  async function onAddPhotos() {
    const picked = await host.pickPhotos();
    if (!picked || !picked.length) return;
    const strip = state.comp.elements.find((e) => e.id === 'strip');
    if (!strip) return;
    let i = 0;
    for (const block of strip.blocks) {
      if (!block.photo && i < picked.length) { block.photo = picked[i++].dataUrl; }
    }
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
    const blob = await exportBlob();
    const url = URL.createObjectURL(blob);
    const a = el('a', { href: url, download: 'post.png' }, {});
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
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
    const post = await host.getPost(id);
    if (post && post.template_json) {
      state.comp = deserialize(post.template_json);
      renderPreview();
      previewBox.scrollIntoView({ block: 'center' });
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

  // init
  renderPreview();
  refreshGallery();
  rootEl.dataset.psReady = '1';
}

function titleText(comp) {
  const t = (comp.elements || []).find((e) => e.id === 'title');
  return t && t.headline ? (t.headline.text || '') : '';
}
```

- [ ] **Step 4: Run to verify it passes (or skips)**

Run: `python -m pytest tests/e2e/test_editor_flow.py -v`
Expected: PASS if Playwright present; SKIP otherwise.

- [ ] **Step 5: Commit**

```bash
git add static/post_studio/editor.js static/post_studio/spike/editor_harness.html tests/e2e/test_editor_flow.py
git commit -m "feat(post-studio): editor.js — controller (template/add-photos/export/save/gallery)"
```

---

### Task 6: Mount the editor in the Post Studio tab + retire the P2a placeholder/gallery JS

Replace the inert P2a placeholder with the editor mount root + a module entry, remove the now-superseded inline gallery JS (`psLoadGallery`/`psOnTabOpen`) and the old `#psGallery` section, point the tab-open dispatcher at the module mount, and update the UI presence tests.

**Files:**
- Modify: `templates.py` (HTML mount point + module entry script; remove the leftover P2a gallery section + slim `psLoadGallery`/`psOnTabOpen` block; repoint the tab dispatcher)
- Modify: `tests/test_post_studio_ui.py`

**Interfaces:**
- Consumes: `/post_studio/editor.js` + `/post_studio/host.js` (served by Task 1).
- Produces: a Post Studio tab whose body is `#ps-editor-root`, mounted once on first tab-open via `window.PostStudioMount()`.

- [ ] **Step 1: Write/adjust the failing UI tests**

In `tests/test_post_studio_ui.py`, replace the gallery-and-JS-presence tests with the new mount shape. Remove these (they assert the retired inline gallery): `test_gallery_container_present`, `test_gallery_js_function_present`, `test_gallery_wired_into_tab_open`, `test_gallery_uses_show_confirm`, `test_gallery_delete_uses_fetch_delete`. Update `test_post_studio_js_functions_present` and add the mount tests:

```python
def test_post_studio_editor_mount_present():
    assert 'id="ps-editor-root"' in HTML_TEMPLATE


def test_post_studio_loads_editor_module():
    assert 'src="/post_studio/editor.js"' in HTML_TEMPLATE
    assert 'from \'/post_studio/host.js\'' in HTML_TEMPLATE or \
           'from "/post_studio/host.js"' in HTML_TEMPLATE


def test_post_studio_tab_open_mounts_editor():
    assert 'PostStudioMount' in HTML_TEMPLATE
    assert "tabName === 'poststudio'" in HTML_TEMPLATE


def test_post_studio_old_inline_generator_gone():
    # The P2a interim inline JS is fully superseded by the ESM editor.
    assert 'function psLoadGallery()' not in HTML_TEMPLATE
    assert 'function psOnTabOpen()' not in HTML_TEMPLATE
    assert 'id="psGallery"' not in HTML_TEMPLATE
```

(Also delete `test_post_studio_js_functions_present` from P2a — it asserted `psOnTabOpen` present, which this task removes.)

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_post_studio_ui.py -v`
Expected: FAIL — mount root + module entry absent; old gallery still present.

- [ ] **Step 3: Replace the tab body (HTML)**

In `templates.py`, the Post Studio tab currently holds the P2a placeholder comment, then the gallery section. Replace from the placeholder comment through the end of the gallery section with a single mount root. Find:

```html
                    <!-- WYSIWYG editor mounts here in P2b; the Pillow generator was retired in P2a. -->

                    <!-- Saved Posts Gallery -->
                    <div class="section-card" style="margin-top:24px;">
                        <h3 style="margin:0 0 16px;font-size:1rem;font-weight:600;" data-i18n="ps_gallery">Saved Posts</h3>
                        <div id="psGallery" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:16px;">
                            <!-- cards injected by psLoadGallery() -->
                        </div>
                        <p id="psGalleryEmpty" class="muted" style="display:none;font-size:0.9em;text-align:center;padding:24px 0;" data-i18n="ps_gallery_empty">No saved posts yet.</p>
                    </div>
```

Replace with:

```html
                    <div id="ps-editor-root" class="section-card" style="padding:20px;"></div>
```

- [ ] **Step 4: Replace the inline PS script with the module entry (JS)**

In `templates.py`, replace the entire slimmed P2a Post Studio `<script>` block (the one containing the `// Post Studio gallery list...` comment, `async function psLoadGallery()`, and `async function psOnTabOpen()`) with the module entry. Find the block bounded by `<script>` … `</script>` that starts with the `// Post Studio gallery list` comment and replace the whole block with:

```html
    <script type="module">
        // Post Studio editor (ESM, served same-origin by /post_studio/<file>).
        import { mountEditor } from '/post_studio/editor.js';
        import { createDesktopHost } from '/post_studio/host.js';
        let _psMounted = false;
        window.PostStudioMount = function () {
            if (_psMounted) return;
            const root = document.getElementById('ps-editor-root');
            if (!root) return;
            mountEditor(root, createDesktopHost());
            _psMounted = true;
        };
    </script>
```

> Note: this is a `type="module"` script with no `'\n'`-in-string hazards, so the normal `HTML_TEMPLATE` escaping trap does not bite here. Keep it free of literal `</script>` substrings.

- [ ] **Step 5: Repoint the tab-open dispatcher**

In `templates.py`, the tab dispatcher calls `psOnTabOpen()`. Replace:

```javascript
            else if (tabName === 'poststudio')   psOnTabOpen().catch(function(){});
```

with:

```javascript
            else if (tabName === 'poststudio')   { if (window.PostStudioMount) window.PostStudioMount(); }
```

- [ ] **Step 6: Verify render + run UI tests + node --check**

Run:
```bash
python -c "import templates; print('template import ok')"
python -m pytest tests/test_post_studio_ui.py -v
```
Then confirm the inline scripts still parse (render the template, extract `<script>` blocks, `node --check` each — the repo's JS-escaping guard):
```bash
python -c "import re,templates,io,pathlib; html=templates.HTML_TEMPLATE; b=re.findall(r'<script(?:\s+type=\"module\")?>(.*?)</script>', html, re.S); [io.open(f'_blk_{i}.js','w',encoding='utf-8').write(x) for i,x in enumerate(b)]; print('blocks',len(b))"
for f in _blk_*.js; do node --check "$f" || echo "PARSE FAIL $f"; done; rm -f _blk_*.js
```
Expected: import ok; UI tests PASS; every block parses (module-entry block uses `import`, which `node --check` accepts for `.mjs`/module syntax — if `node --check` rejects bare `import` in a `.js`, rename the temp to `.mjs` in the check; the goal is "the JS is syntactically valid").

- [ ] **Step 7: Commit**

```bash
git add templates.py tests/test_post_studio_ui.py
git commit -m "feat(post-studio): mount the ESM editor in the tab; retire P2a inline gallery JS"
```

---

### Task 7: Full-portal Playwright smoke (end-to-end, importorskip)

A behavioral smoke against the real Flask server: log in, open the Post Studio tab, pick a template, add a photo (drive the hidden file input directly), see the preview, Save, see it in the gallery, reopen it. Guarded so it skips cleanly where Playwright/server startup is unavailable (per memory, in-env Playwright is sometimes blocked).

**Files:**
- Create: `tests/e2e/test_post_studio_smoke.py`

**Interfaces:**
- Consumes: a running app instance (the test starts the Flask app on an ephemeral port against a temp DB), a seeded login. Reuse the login/bootstrap pattern from the repo's existing portal Playwright smokes if present; otherwise the test documents the manual steps and skips.

- [ ] **Step 1: Write the smoke (skip-guarded)**

Create `tests/e2e/test_post_studio_smoke.py`:

```python
"""End-to-end Post Studio smoke. Skips unless Playwright AND a portal test
harness are available; documents the manual checklist either way."""
import pytest

pytest.importorskip("playwright.sync_api",
                    reason="Playwright not installed in this environment")

# Reuse the project's portal e2e bootstrap if one exists; otherwise skip with a
# clear reason so this never blocks the suite in headless/CI envs.
_portal = pytest.importorskip(
    "tests.e2e.portal_harness",
    reason="No portal Playwright bootstrap (manual smoke — see checklist below)",
)


def test_post_studio_create_save_reopen(live_portal_page):
    page = live_portal_page                      # logged-in portal page fixture
    page.click("[data-tab='poststudio']")
    page.wait_for_selector("#ps-editor-root [data-ps-preview]")
    page.click("[data-ps-template='before_after']")
    # Drive the hidden file input the desktop host creates on pickPhotos():
    page.once("filechooser", lambda fc: fc.set_files(_one_png_path()))
    page.click("[data-ps-action='add-photos']")
    page.wait_for_function("() => document.querySelectorAll('[data-ps-stage] img').length >= 1")
    page.click("[data-ps-action='save']")
    page.wait_for_selector("[data-ps-gallery-item]")
    page.click("[data-ps-action='reopen']")
    page.wait_for_selector("[data-ps-stage]")
```

> If the repo has no portal Playwright bootstrap, this test SKIPS. Record the manual checklist in the commit body / the P2b PR description: **(1)** Post Studio tab opens to the editor; **(2)** picking each template re-renders the canvas; **(3)** Add photos → photos appear in the cards with ①② badges; **(4)** Download saves a PNG; **(5)** Save → the post appears in the gallery; **(6)** Edit reopens it and re-renders; **(7)** EN and AR both render (toggle language; Arabic labels show, layout is RTL-sane).

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/e2e/test_post_studio_smoke.py -v`
Expected: PASS if a portal harness + Playwright exist; otherwise SKIP (clean).

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_post_studio_smoke.py
git commit -m "test(post-studio): full-portal editor smoke (importorskip-guarded)"
```

---

### Task 8: Phase-gate verification (P2b)

**Files:** none (verification only).

- [ ] **Step 1: Full Python suite**

Run: `python -m pytest tests/` then check the exit code (summary suppressed): PowerShell `$LASTEXITCODE`.
Expected: `0`.

- [ ] **Step 2: JS suites**

Run: `node --test tests/js/`
Expected: exit `0` (composition + host tests).

- [ ] **Step 3: Editor render/flow checks**

Run: `python -m pytest tests/e2e/test_editor_render.py tests/e2e/test_editor_flow.py -v`
Expected: PASS if Playwright present, otherwise SKIP — either is acceptable for the gate, but if PASS is available, it must be green.

- [ ] **Step 4: Import + template render smoke**

Run: `python -c "import dental_clinic, templates; print('ok')"` and confirm `GET /post_studio/editor.js` would resolve (the file exists under `static/post_studio/`).

- [ ] **Step 5: (No commit.)** P2b is complete — the editor is live in the desktop tab (structural styling). Author the **P3** plan (premium 4-theme token system + fully-styled starter templates + bundled/inlined font set), seeding it from `render.js`'s `THEME_BG` placeholder (which P3 replaces with the real token map) and the `composition.js` per-element `font`/`color` fields.

---

## Self-Review

- **Spec coverage (P2 "editor core" scope):** live WYSIWYG canvas → Task 3 (`render.js`); client-side PNG export, fully offline → Task 2 (`rasterize.js`, vendored from the validated spike); host-agnostic editor + desktop host adapter (the `PostStudioHost` shape from the spec's Architecture section) → Tasks 4 (`host.js`) & 5 (`editor.js`); save/load/list/delete wired to the new spec → Task 5 against the P2a endpoints, with the desktop host using the CSRF-wrapped `fetch`; the tab UI (left controls / center canvas / gallery) → Tasks 5–6 (Inspector + drag are explicitly P4); same renderer on both hosts via relative-import ESM served same-origin and frozen-bundled → Task 1; EN/AR → the editor `STR` map. Deferred to **P3** (correctly, by dependency): the 4 premium themes, fully-styled starter templates, and the bundled font set — `render.js` ships one neutral per-theme background placeholder. Deferred to **P4**: drag-positioning + snap guides, the per-element typography inspector, the phase add/reorder/insert UI (the `composition.js` mutators exist from P2a, unused until P4), and editable title/subline/doctor text. Deferred to **P6**: the mobile host (the modules are already host-agnostic + relative-import, so P6 adds only a Flutter asset shell + a Dart-bridge host). ✓
- **Placeholder scan:** every code step contains the full file or the exact old/new text. The deliberate, documented simplifications are: structural (not premium) styling in `render.js` (P3 scope, flagged), and photos stored as data-URLs inside `template_json` (a stated P2b decision that makes export + round-trip work with zero extra routes; file-based photo storage is a noted future optimization). Neither is a TODO. The Task-2 render-test ordering caveat is called out with the recommended fix (do Task 3's `render.js` before running it). ✓
- **Type/name consistency:** `renderComposition`/`EXPORT_PX` defined in Task 3 are imported by `editor.js` (Task 5) and the harness (Task 2); `rasterizeToPngBlob(node, scale)` defined in Task 2 is called by `editor.js`; `createDesktopHost()` (Task 4) returns exactly the 5 methods the harness fake host mirrors and `editor.js` calls (`pickPhotos`/`savePost`/`listPosts`/`getPost`/`deletePost`); `savePost(png, templateJson, meta)`'s multipart fields (`image`/`template_json`/`theme`/`size`/`title`) match the P2a `POST /api/posts` contract; the `/post_studio/<file>` route (Task 1) serves the exact relative-imported module filenames; `window.PostStudioMount` (Task 6 entry) matches the dispatcher call (Task 6 Step 5); `data-ps-*` hooks used by the Playwright tests (`data-ps-stage`, `data-ps-preview`, `data-ps-action`, `data-ps-gallery-item`, `data-ps-template`) are all emitted by `render.js`/`editor.js`. ✓
- **Interim-state honesty:** Task 6 removes the superseded P2a inline gallery JS so nothing dead remains; the tab is fully working (template → photos → export → save → reopen) at end of P2b, with styling/editing depth deferred to P3/P4 as the spec's build order intends. Acceptable because P2b–P6 stack on the branch with no interim release. ✓
