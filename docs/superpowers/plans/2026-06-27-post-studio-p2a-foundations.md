# Post Studio Redesign — Phase 2a (Foundations & Rasterizer Spike) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** De-risk and build the non-UI foundations of the client-side Post Studio editor — validate the client-side PNG rasterizer, reshape the data model, build the pure composition state model, rework the storage endpoints to the new spec, and retire the server-side Pillow render engine.

**Architecture:** P2 (editor core) is split into two stacked, independently-testable slices because it spans multiple subsystems and contains one genuine implementation risk (the rasterizer). **P2a (this plan)** delivers everything the interactive editor sits on top of: a validated rasterization technique, the `template_json` schema, a DOM-free composition state model (node-tested), and the reworked Flask endpoints — and removes the old Pillow engine. **P2b** (the editor HTML/JS bundle, canvas renderer, host adapter, client export, tab wiring, Playwright smoke) is authored just-in-time after P2a, because its export and canvas signatures depend on the spike's outcome and the concrete `composition.js` API that P2a locks in.

**Interim branch state (expected, acceptable):** retiring the Pillow engine in this slice removes `post_studio.render_post`, so the **existing Post Studio tab UI stops working at the end of P2a** (its current JS still calls the removed preview/save-with-photos flow). That is fine: we are stacking P2a–P6 on `feat/post-studio` with **no intermediate PR or release** (decided 2026-06-27 — hold the PR until the editor replaces Pillow). P2b restores a working tab. The plan removes the now-dead old tab JS as part of Task 7 so nothing calls a missing endpoint.

**Tech Stack:** Flask (`dental_clinic.py`), SQLite, Pillow (kept for *upload hygiene only* — validation + downscale; no longer for rendering), pure ESM JavaScript run under `node --test` (Node's built-in runner, no new deps), Chromium (WebView2 desktop / Android System WebView mobile) for the spike, Playwright for the spike's automated check.

## Global Constraints

- **No CDN / no remote assets at runtime** — everything inlined or bundled (project rule). Vendoring (copying source into the repo) is allowed; runtime fetches to a CDN are not.
- **EN/AR throughout, RTL-aware** — every user-facing string has `en:` and `ar:` keys. (P2a is mostly non-UI; the constraint binds P2b, but any P2a-introduced copy obeys it.)
- **Immutability** — the composition state model returns **new** objects; it never mutates its inputs (project coding-style rule; uses `structuredClone`).
- **Clean slate / pre-release** — `marketing_posts` carries no production data, so the schema may be altered freely (spec §Data model). Dev databases may hold throwaway test rows; the migration handles them without requiring manual DB deletion.
- **`HTML_TEMPLATE` is a normal Python string** — a JS `'\n'` becomes a real newline and breaks the inline `<script>`. Double-escape (`'\\n'`). (Binds Task 7's small JS deletion.)
- **`web_assets.py` cannot be opened by the Read/Edit tools** (~249k tokens of inlined base64). If a task must touch it, use an idempotent, anchor-asserting Python script (the pattern P1 Task 1 used). P2a does **not** need to touch `web_assets.py`.
- **Commits:** conventional-commit messages, no attribution footer (repo setting).
- **Gate:** `python -m pytest tests/` exits `0` (the repo suppresses the pytest summary — check `$LASTEXITCODE` / the exit code, not the printed text) **and** `node --test tests/js/` exits `0`.

## File Structure (decomposition locked here)

- **Create** `static/post_studio/composition.js` — pure, DOM-free ESM composition state model (default-template construction, block add/remove/reorder/insert with badge renumbering, serialize/deserialize round-trip). The single source of truth for the `template_json` shape, consumed by both hosts in P2b/P6.
- **Create** `static/post_studio/package.json` — `{"type":"module"}`, so Node treats the `.js` modules in this dir as ESM (there is no root `package.json`; `.js` would otherwise be parsed as CommonJS and `export` would throw under `node --test`). Keeps the `.js` extension, which serves cleanest as `text/javascript` to the browser/Flutter hosts in P2b/P6.
- **Create** `static/post_studio/spike/spike.html` — self-contained rasterizer spike harness (throwaway-ish; kept in-repo as living proof + future reference).
- **Create** `tests/js/composition.test.mjs` — `node --test` unit tests for the state model.
- **Create** `tests/e2e/test_rasterizer_spike.py` — Playwright check that the spike rasterizes a hard composition to a correctly-sized, non-blank, untainted PNG.
- **Create** `docs/superpowers/notes/2026-06-27-rasterizer-spike-decision.md` — records the spike outcome + the chosen export technique for P2b.
- **Modify** `dental_clinic.py` — `marketing_posts` schema + migration; new `POST /api/posts/photos`; reworked `POST /api/posts` (accept client PNG + `template_json`); new `GET /api/posts/<id>` (return `template_json`); open-read gate for `GET /api/posts/<id>`; remove `POST /api/posts/preview` + `_build_spec_from_request`; remove `import post_studio`; delete-post also removes the post's photo dir.
- **Modify** `templates.py` — remove the now-dead old generator JS (`psSave`/`psDownload` preview-and-form-upload path) so nothing calls a removed endpoint. (Leave the tab shell + gallery list; P2b replaces the body.)
- **Delete** `post_studio.py`, `post_themes.py`, `tests/test_post_studio_engine.py`, `tests/golden/post_studio/*` — the retired engine + its golden pixel tests.
- **Modify** `tests/test_post_studio_api.py` — drop preview / render-rollback tests; rewrite save → list → get-spec → serve → delete around the new PNG+`template_json` contract.

## Phase roadmap (context)

This plan covers **P2a only**. Spec: `docs/superpowers/specs/2026-06-27-post-studio-redesign.md`. P1 (cleanups) is DONE. After P2a: **P2b** (editor bundle + desktop wiring), then P3 themes/templates/fonts, P4 deep customization, P5 desktop QA, P6 mobile parity. P2b–P6 authored just-in-time.

---

### Task 1: Rasterizer spike — validate the client-side capture technique (DECISION GATE)

**Why first:** the spec flags client-side PNG export as the single open risk. Before any editor code commits to it, prove the technique (SVG `<foreignObject>` → `<canvas>` → `toDataURL`, the same mechanism `html-to-image` wraps) survives the *hard* cases the reference design needs: a radial-gradient background, a rounded card with border/glow, mixed-weight + letter-spaced text, an embedded same-origin image, **Arabic** text, and a bundled web font — all at full export resolution, **without tainting the canvas** (which would make `toDataURL` throw a `SecurityError`).

**Files:**
- Create: `static/post_studio/spike/spike.html`
- Create: `tests/e2e/test_rasterizer_spike.py`
- Create: `docs/superpowers/notes/2026-06-27-rasterizer-spike-decision.md`

**Interfaces:**
- Consumes: nothing (standalone; loaded via `file://`).
- Produces: a documented decision (`html_to_image_foreignobject` ✔ or fall back to `canvas2d`) that Task-gates P2b's export implementation. Exposes, for the test, `window.__spikeRasterize()` → resolves to a PNG data URL, and `window.__spikeError` (string|null).

- [ ] **Step 1: Write the spike harness**

Create `static/post_studio/spike/spike.html`. It must be fully self-contained (no network). Use a tiny inlined font (any small base64 TTF already in `fonts/` re-encoded, OR `@font-face` pointing at a `data:` URL — to keep the file readable, embed a short data-URL font; the exact face does not matter, only that a `@font-face` web font renders into the raster). Embed the test image as a `data:` URL (a tiny 2×2 PNG is fine — it proves images are captured without tainting).

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Post Studio rasterizer spike</title>
<style>
  /* A bundled web font via data URL (small placeholder face — fidelity of the
     glyphs is not under test; that a web font rasterizes is). */
  @font-face {
    font-family: 'SpikeFont';
    src: url('data:font/ttf;base64,AAEAAAALAIAAAwAwT1MvMg8SBfQAAAC8AAAAYGNtYXAADQHqAAABHAAAAExnYXNw//8AAwAAAWgAAAAIZ2x5ZgAAAAAAAAFwAAAAAGhlYWQ...REPLACE_WITH_A_REAL_SMALL_TTF_BASE64...') format('truetype');
    font-weight: 400 800;
  }
  #stage {
    width: 1080px; height: 1080px; position: relative; overflow: hidden;
    /* radial-glow background — the non-flat case */
    background:
      radial-gradient(60% 50% at 50% 38%, #15324e 0%, #0b1f33 55%, #060f1c 100%);
    font-family: 'SpikeFont', system-ui, sans-serif;
  }
  .card {
    position: absolute; left: 90px; top: 360px; width: 420px; height: 420px;
    border-radius: 28px; border: 1px solid rgba(120,200,220,.35);
    box-shadow: 0 0 40px rgba(60,160,180,.25) inset; overflow: hidden;
  }
  .card img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .headline { position: absolute; left: 0; right: 0; top: 90px; text-align: center;
    color: #fff; font-weight: 800; font-size: 64px; letter-spacing: 1px; }
  .subline  { position: absolute; left: 0; right: 0; top: 170px; text-align: center;
    color: #5fd3c8; font-weight: 500; font-size: 40px; }
  .name { position: absolute; left: 0; right: 0; bottom: 60px; text-align: center;
    color: #c9a227; font-weight: 700; font-size: 34px; letter-spacing: 4px; }
  .ar { position: absolute; left: 0; right: 0; bottom: 120px; text-align: center;
    color: #cfd8e3; font-size: 30px; direction: rtl; }
</style>
</head>
<body>
  <div id="stage">
    <div class="headline">Root Canal Treatment</div>
    <div class="subline">for Lower Molar</div>
    <div class="card"><img alt="" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEUlEQVR4nGNkYPjPgAcw4pMEAB0EAv9G2k0xAAAAAElFTkSuQmCC"></div>
    <div class="ar">علاج عصب الضرس السفلي</div>
    <div class="name">DR. WASFY BARZAQ</div>
  </div>

  <script>
    // Minimal foreignObject rasterizer — the exact core html-to-image uses.
    // Captures #stage at full resolution honoring devicePixelRatio.
    window.__spikeError = null;
    async function rasterize(node, scale) {
      const w = node.offsetWidth, h = node.offsetHeight;
      // Serialize the node (with its computed styles already inline via CSS above)
      // into an SVG <foreignObject>.
      const xhtml = new XMLSerializer().serializeToString(node);
      const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '">' +
          '<foreignObject x="0" y="0" width="100%" height="100%">' +
            '<div xmlns="http://www.w3.org/1999/xhtml">' + xhtml + '</div>' +
          '</foreignObject>' +
        '</svg>';
      const svgUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
      const img = new Image();
      img.width = w; img.height = h;
      await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = svgUrl; });
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(w * scale);
      canvas.height = Math.round(h * scale);
      const ctx = canvas.getContext('2d');
      ctx.scale(scale, scale);
      ctx.drawImage(img, 0, 0);
      return canvas.toDataURL('image/png'); // throws SecurityError if the canvas is tainted
    }

    window.__spikeRasterize = async function () {
      try {
        await document.fonts.ready;
        const scale = window.devicePixelRatio || 1;
        return await rasterize(document.getElementById('stage'), scale);
      } catch (e) {
        window.__spikeError = String(e);
        throw e;
      }
    };
  </script>
</body>
</html>
```

> Note for the implementer: replace the `REPLACE_WITH_A_REAL_SMALL_TTF_BASE64` marker with the base64 of any small TTF (e.g. base64-encode an existing file under `fonts/` and paste it, or use a stripped subset). The harness must contain a real decodable font so `@font-face` actually loads — that is part of what the spike validates.

- [ ] **Step 2: Write the failing Playwright check**

Create `tests/e2e/test_rasterizer_spike.py`:

```python
import base64
import struct
from pathlib import Path

import pytest

playwright_sync = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright not installed in this environment",
)
from playwright.sync_api import sync_playwright  # noqa: E402

SPIKE = (Path(__file__).resolve().parents[1].parent
         / "static" / "post_studio" / "spike" / "spike.html")


def _png_size(data: bytes):
    # PNG: 8-byte signature, then IHDR (length+type+width+height...)
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_spike_rasterizes_hard_composition_without_taint():
    url = SPIKE.as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2)
        page.goto(url)
        # Run the in-page rasterizer; this rejects on SecurityError (tainted canvas).
        data_url = page.evaluate("() => window.__spikeRasterize()")
        err = page.evaluate("() => window.__spikeError")
        browser.close()

    assert err is None, f"rasterizer threw: {err}"
    assert data_url.startswith("data:image/png;base64,"), data_url[:40]
    raw = base64.b64decode(data_url.split(",", 1)[1])
    w, h = _png_size(raw)
    # 1080 logical px at device_scale_factor=2 → 2160 device px.
    assert (w, h) == (2160, 2160), (w, h)
    # Non-blank: a fully-uniform image would compress tiny. The gradient + text
    # guarantees a substantial PNG.
    assert len(raw) > 20_000, f"suspiciously small PNG: {len(raw)} bytes"
```

- [ ] **Step 3: Run it to verify the gate**

Run: `python -m pytest tests/e2e/test_rasterizer_spike.py -v`
Expected: **PASS** if the technique works (this *is* the spike result). If Playwright is not installed, the test **skips** (`importorskip`) — in that case, validate manually: open `static/post_studio/spike/spike.html` in the desktop WebView (WebView2) via a throwaway `python -c` Flask route or `file://`, call `await window.__spikeRasterize()` in the devtools console, and confirm it returns a `data:image/png` URL (no `SecurityError`) and the image shows the gradient + Arabic + gold name.

- [ ] **Step 4: Record the decision**

Create `docs/superpowers/notes/2026-06-27-rasterizer-spike-decision.md` with the outcome:

```markdown
# Rasterizer spike decision (2026-06-27)

Technique tested: SVG <foreignObject> → Image → canvas.drawImage → canvas.toPng
(the core of html-to-image), against radial-gradient bg, rounded/glow card,
letter-spaced + mixed-weight text, embedded same-origin (data-URL) image,
Arabic RTL text, and a @font-face web font, at devicePixelRatio scale.

Result: <PASS | FAIL>.
- Canvas taint (toDataURL SecurityError): <none | observed on: …>
- Fidelity issues: <none | …>

Decision for P2b export:
- If PASS → adopt a vendored `html-to-image` (or the minimal foreignObject
  rasterizer above, hardened) as `static/post_studio/vendor/rasterize.js`.
  Embed fonts as data URLs and ensure all <img> are same-origin/data-URL
  before capture; await document.fonts.ready.
- If FAIL → fall back to a hand-rolled Canvas 2D renderer that mirrors the
  composition (separate just-in-time P2b task). Reason recorded above.
```

- [ ] **Step 5: Commit**

```bash
git add static/post_studio/spike/spike.html tests/e2e/test_rasterizer_spike.py docs/superpowers/notes/2026-06-27-rasterizer-spike-decision.md
git commit -m "spike(post-studio): validate client-side foreignObject->canvas PNG export"
```

---

### Task 2: Reshape the `marketing_posts` schema (`template_json`; drop `photo_count`/`labels_json`)

The saved post **is** its editable spec. Add `template_json`; drop the Pillow-era `photo_count` (NOT NULL) and `labels_json`. Clean slate, but dev DBs may hold old-shape rows — migrate them without manual deletion.

**Files:**
- Modify: `dental_clinic.py:1213-1226` (the `CREATE TABLE marketing_posts` block)
- Modify: `dental_clinic.py` `init_database` (add a guarded one-time rebuild for old-shape DBs, right after the CREATE TABLE)
- Test: `tests/test_post_studio_api.py`

**Interfaces:**
- Consumes: existing `ensure_table_column(cursor, table, col, decl)` helper, `init_database()`.
- Produces: a `marketing_posts` table with columns `id, title, theme, size, doctor_name, template_json, file_name, file_path, created_at` and **no** `photo_count`/`labels_json`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_post_studio_api.py`:

```python
import sqlite3 as _sqlite3


def test_marketing_posts_schema_has_template_json_not_photo_count(client):
    # client fixture has already run init_database() against a fresh temp DB.
    conn = _sqlite3.connect(dental_clinic.DB_NAME)
    cols = {row[1] for row in conn.execute('PRAGMA table_info(marketing_posts)')}
    conn.close()
    assert 'template_json' in cols
    assert 'photo_count' not in cols
    assert 'labels_json' not in cols
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_post_studio_api.py::test_marketing_posts_schema_has_template_json_not_photo_count -v`
Expected: FAIL — `photo_count` still present, `template_json` absent.

- [ ] **Step 3: Update the CREATE TABLE**

In `dental_clinic.py`, replace:

```python
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS marketing_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            theme TEXT NOT NULL,
            size TEXT NOT NULL,
            doctor_name TEXT,
            photo_count INTEGER NOT NULL,
            labels_json TEXT,
            file_name TEXT,
            file_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
```

with:

```python
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS marketing_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            theme TEXT NOT NULL,
            size TEXT NOT NULL,
            doctor_name TEXT,
            template_json TEXT,
            file_name TEXT,
            file_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Pre-release migration: rebuild old-shape DBs (those still carrying the
    # Pillow-era photo_count/labels_json) to the new shape. No production data
    # exists, so dropping the table is safe; this spares a manual DB delete on
    # dev machines. New-shape DBs that merely lack template_json get the column.
    _mp_cols = {row[1] for row in cursor.execute('PRAGMA table_info(marketing_posts)')}
    if 'photo_count' in _mp_cols or 'labels_json' in _mp_cols:
        cursor.execute('DROP TABLE marketing_posts')
        cursor.execute('''
            CREATE TABLE marketing_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                theme TEXT NOT NULL,
                size TEXT NOT NULL,
                doctor_name TEXT,
                template_json TEXT,
                file_name TEXT,
                file_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    else:
        ensure_table_column(cursor, 'marketing_posts', 'template_json', 'TEXT')
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_post_studio_api.py::test_marketing_posts_schema_has_template_json_not_photo_count -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_post_studio_api.py
git commit -m "feat(post-studio): marketing_posts stores template_json (drop photo_count/labels_json)"
```

---

### Task 3: Composition state model — default template + serialize round-trip (pure ESM, node-tested)

A DOM-free module that owns the `template_json` shape: build a default composition from a starter-template key, and serialize/deserialize it losslessly with validation. (Block add/remove/reorder/insert lands in Task 4 — split so a reviewer can gate construction independently from mutation.)

**Files:**
- Create: `static/post_studio/package.json` (`{"type":"module"}` — makes `.js` here ESM under Node)
- Create: `static/post_studio/composition.js`
- Create: `tests/js/composition.test.mjs`

**Interfaces:**
- Consumes: `structuredClone` (global in Node 17+ and all target Chromium WebViews).
- Produces (all exported from `composition.js`, consumed by Task 4 and P2b):
  - `MAX_BLOCKS = 6`, `SIZES = ['square','portrait','story']`, `TEMPLATES = ['before_after','multi_phase','quad_grid','single_feature']`
  - `defaultComposition(template: string, opts?: { doctorName?: string }) -> Composition`
  - `serialize(comp: Composition) -> string`
  - `deserialize(json: string) -> Composition` (throws `Error` on invalid version/size)
  - A `Composition` is `{ version: 1, size: string, theme: string, elements: Element[] }` where elements include a `title`, a `photoStrip` (`{ id:'strip', type:'photoStrip', layout, blocks: Block[], labelStyle }`), and a `doctorName`. A `Block` is `{ photo: string|null, badge: number, label: string }`.

- [ ] **Step 1: Write the failing tests**

Create `tests/js/composition.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MAX_BLOCKS, SIZES, TEMPLATES,
  defaultComposition, serialize, deserialize,
} from '../../static/post_studio/composition.js';

test('constants', () => {
  assert.equal(MAX_BLOCKS, 6);
  assert.deepEqual(SIZES, ['square', 'portrait', 'story']);
  assert.ok(TEMPLATES.includes('before_after'));
});

test('defaultComposition(before_after) has title + 2-block strip + doctor', () => {
  const c = defaultComposition('before_after', { doctorName: 'DR. WASFY BARZAQ' });
  assert.equal(c.version, 1);
  assert.ok(SIZES.includes(c.size));
  const ids = c.elements.map((e) => e.id);
  assert.deepEqual(ids, ['title', 'strip', 'doctor']);
  const strip = c.elements.find((e) => e.id === 'strip');
  assert.equal(strip.blocks.length, 2);
  assert.deepEqual(strip.blocks.map((b) => b.badge), [1, 2]);
  const doctor = c.elements.find((e) => e.id === 'doctor');
  assert.equal(doctor.text, 'DR. WASFY BARZAQ');
});

test('defaultComposition is immutable across calls (no shared refs)', () => {
  const a = defaultComposition('before_after');
  const b = defaultComposition('before_after');
  a.elements.find((e) => e.id === 'strip').blocks.push({ photo: null, badge: 9, label: 'x' });
  const bStrip = b.elements.find((e) => e.id === 'strip');
  assert.equal(bStrip.blocks.length, 2, 'second composition must not share block arrays');
});

test('unknown template throws', () => {
  assert.throws(() => defaultComposition('nope'), /unknown template/i);
});

test('serialize/deserialize round-trips losslessly', () => {
  const c = defaultComposition('multi_phase', { doctorName: 'DR. X' });
  const back = deserialize(serialize(c));
  assert.deepEqual(back, c);
});

test('deserialize rejects wrong version and bad size', () => {
  assert.throws(() => deserialize(JSON.stringify({ version: 2, size: 'square', theme: 't', elements: [] })), /version/i);
  assert.throws(() => deserialize(JSON.stringify({ version: 1, size: 'wat', theme: 't', elements: [] })), /size/i);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/composition.test.mjs`
Expected: FAIL — module `static/post_studio/composition.js` does not exist.

- [ ] **Step 3: Implement `composition.js` (and the ESM marker)**

First create `static/post_studio/package.json` so Node parses this dir's `.js` as ESM:

```json
{ "type": "module" }
```

Then create `static/post_studio/composition.js`:

```javascript
// Pure, DOM-free composition state for Post Studio.
// Single source of truth for the template_json shape. ESM so it loads in
// node --test AND in the WebView (<script type="module">). Never mutates inputs.

export const MAX_BLOCKS = 6;
export const SIZES = ['square', 'portrait', 'story'];
export const TEMPLATES = ['before_after', 'multi_phase', 'quad_grid', 'single_feature'];

const DEFAULT_THEME = 'dark_premium';

// Element factory helpers — geometry/typography here are structural defaults
// only; P3 themes restyle them. Positions are fractional (0–1), size-independent.
function titleElement() {
  return {
    id: 'title', type: 'title', x: 0.5, y: 0.10, align: 'center',
    headline: { text: 'Procedure Title', font: 'playfair', size: 64, weight: 700, color: '#ffffff', letterSpacing: 0 },
    subline: { text: 'Subtitle', font: 'manrope', size: 40, weight: 500, color: '#5fd3c8', letterSpacing: 0 },
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
    labelStyle: { font: 'manrope', size: 28, weight: 600, color: '#cfd8e3' },
  });
}

function doctorElement(doctorName) {
  return {
    id: 'doctor', type: 'doctorName', x: 0.5, y: 0.93, align: 'center',
    text: doctorName || '',
    font: 'manrope', size: 34, weight: 700, color: '#c9a227', letterSpacing: 4,
  };
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
  return {
    version: 1,
    size: 'square',
    theme: DEFAULT_THEME,
    elements: [
      titleElement(),
      stripElement(seed.labels, seed.layout),
      doctorElement(opts.doctorName),
    ],
  };
}

export function serialize(comp) {
  return JSON.stringify(comp);
}

export function deserialize(json) {
  const c = typeof json === 'string' ? JSON.parse(json) : json;
  if (c.version !== 1) throw new Error(`unsupported version: ${c.version}`);
  if (!SIZES.includes(c.size)) throw new Error(`invalid size: ${c.size}`);
  return structuredClone(c);
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `node --test tests/js/composition.test.mjs`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add static/post_studio/package.json static/post_studio/composition.js tests/js/composition.test.mjs
git commit -m "feat(post-studio): pure composition state model (default template + round-trip)"
```

---

### Task 4: Composition block operations — add / remove / reorder / insert with badge renumber (cap 6)

Pure mutators (return new compositions) over the `photoStrip` blocks, each keeping badges contiguous `1..n` and enforcing the 6-block cap.

**Files:**
- Modify: `static/post_studio/composition.js`
- Modify: `tests/js/composition.test.mjs`

**Interfaces:**
- Consumes: `renumber`, `MAX_BLOCKS`, the `Composition`/`Block` shapes from Task 3.
- Produces (exported, consumed by P2b's phase controls):
  - `addBlock(comp, label?: string) -> Composition` (appends; throws if already at `MAX_BLOCKS`)
  - `removeBlock(comp, index: number) -> Composition`
  - `reorderBlock(comp, from: number, to: number) -> Composition`
  - `insertBlock(comp, index: number, label?: string) -> Composition` (throws if at cap)

- [ ] **Step 1: Write the failing tests**

Append to `tests/js/composition.test.mjs`:

```javascript
import { addBlock, removeBlock, reorderBlock, insertBlock } from '../../static/post_studio/composition.js';

function strip(c) { return c.elements.find((e) => e.id === 'strip'); }

test('addBlock appends and renumbers', () => {
  const c = addBlock(defaultComposition('before_after'), 'Follow-up');
  assert.deepEqual(strip(c).blocks.map((b) => b.badge), [1, 2, 3]);
  assert.equal(strip(c).blocks[2].label, 'Follow-up');
});

test('addBlock enforces the 6-block cap', () => {
  let c = defaultComposition('quad_grid'); // 4 blocks
  c = addBlock(c); c = addBlock(c);          // 6
  assert.equal(strip(c).blocks.length, MAX_BLOCKS);
  assert.throws(() => addBlock(c), /max|cap|6/i);
});

test('removeBlock drops one and renumbers', () => {
  const c = removeBlock(defaultComposition('multi_phase'), 1); // drop 'During'
  assert.deepEqual(strip(c).blocks.map((b) => b.label), ['Before', 'After']);
  assert.deepEqual(strip(c).blocks.map((b) => b.badge), [1, 2]);
});

test('reorderBlock moves and renumbers', () => {
  const c = reorderBlock(defaultComposition('multi_phase'), 2, 0); // After -> front
  assert.deepEqual(strip(c).blocks.map((b) => b.label), ['After', 'Before', 'During']);
  assert.deepEqual(strip(c).blocks.map((b) => b.badge), [1, 2, 3]);
});

test('insertBlock inserts between and renumbers', () => {
  const c = insertBlock(defaultComposition('before_after'), 1, 'Mid');
  assert.deepEqual(strip(c).blocks.map((b) => b.label), ['Before Treatment', 'Mid', 'After Treatment']);
  assert.deepEqual(strip(c).blocks.map((b) => b.badge), [1, 2, 3]);
});

test('mutators do not mutate their input', () => {
  const base = defaultComposition('before_after');
  addBlock(base, 'x');
  assert.equal(strip(base).blocks.length, 2);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/composition.test.mjs`
Expected: FAIL — `addBlock` etc. are not exported.

- [ ] **Step 3: Implement the mutators**

Append to `static/post_studio/composition.js`:

```javascript
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `node --test tests/js/composition.test.mjs`
Expected: PASS (all tests, old + new).

- [ ] **Step 5: Commit**

```bash
git add static/post_studio/composition.js tests/js/composition.test.mjs
git commit -m "feat(post-studio): block add/remove/reorder/insert with badge renumber + cap"
```

---

### Task 5: Photo-upload endpoint — `POST /api/posts/photos` (validate + downscale, staged storage)

The client uploads source photos *before* a post id exists. Validate at the boundary (image type, count 1–6, size cap, downscale oversized) and stage them under `UPLOAD_FOLDER/posts/_staging/`; return server-safe relative paths the client later passes to save. Pillow stays for this hygiene step only (not rendering).

**Files:**
- Modify: `dental_clinic.py` (add the route near the other posts routes; keep `import` of `secure_filename` / `uuid` — add if missing)
- Test: `tests/test_post_studio_api.py`

**Interfaces:**
- Consumes: `UPLOAD_FOLDER`, `_PILImage` (the existing Pillow alias), the login gate (write → requires session).
- Produces: `POST /api/posts/photos` (multipart, field `photo`, 1–6 files) → `200 {'photos': ['posts/_staging/<uuid>.jpg', ...]}`; `400` on zero/too-many/invalid; `401` unauthenticated.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_post_studio_api.py`:

```python
def test_photos_requires_login(client):
    assert client.post('/api/posts/photos').status_code == 401


def test_photos_upload_returns_staged_paths(client):
    _login(client)
    r = client.post('/api/posts/photos',
                    data={'photo': [(io.BytesIO(_png()), 'a.png'),
                                    (io.BytesIO(_png()), 'b.png')]},
                    content_type='multipart/form-data')
    assert r.status_code == 200
    paths = r.get_json()['photos']
    assert len(paths) == 2
    assert all(p.startswith('posts/_staging/') for p in paths)
    assert all((dental_clinic.UPLOAD_FOLDER / p).exists() for p in paths)


def test_photos_rejects_zero_and_too_many(client):
    _login(client)
    assert client.post('/api/posts/photos', data={},
                       content_type='multipart/form-data').status_code == 400
    seven = [(io.BytesIO(_png()), f'p{i}.png') for i in range(7)]
    assert client.post('/api/posts/photos', data={'photo': seven},
                       content_type='multipart/form-data').status_code == 400


def test_photos_rejects_non_image(client):
    _login(client)
    r = client.post('/api/posts/photos',
                    data={'photo': [(io.BytesIO(b'not an image'), 'x.png')]},
                    content_type='multipart/form-data')
    assert r.status_code == 400
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_post_studio_api.py -k photos -v`
Expected: FAIL — route `/api/posts/photos` does not exist (login test sees the prefix gate 401, but the upload/reject tests fail).

- [ ] **Step 3: Implement the route**

In `dental_clinic.py`, add near the other `/api/posts` routes (and ensure `import uuid` and `from werkzeug.utils import secure_filename` exist at the top — add if missing):

```python
_MAX_POST_PHOTOS = 6
_POST_PHOTO_MAX_EDGE = 2000  # px; downscale longer edge to keep files sane


@app.route('/api/posts/photos', methods=['POST'])
def posts_photos():
    files = [f for f in request.files.getlist('photo') if f and f.filename]
    if not files:
        return jsonify({'error': 'No photos uploaded'}), 400
    if len(files) > _MAX_POST_PHOTOS:
        return jsonify({'error': f'At most {_MAX_POST_PHOTOS} photos'}), 400
    staging = UPLOAD_FOLDER / 'posts' / '_staging'
    staging.mkdir(parents=True, exist_ok=True)
    out = []
    for f in files:
        try:
            img = _PILImage.open(f.stream)
            img.verify()                 # reject corrupt/non-images
            f.stream.seek(0)
            img = _PILImage.open(f.stream).convert('RGB')
        except Exception:                # noqa: BLE001
            return jsonify({'error': 'One of the files is not a valid image'}), 400
        longest = max(img.size)
        if longest > _POST_PHOTO_MAX_EDGE:
            scale = _POST_PHOTO_MAX_EDGE / longest
            img = img.resize((max(1, round(img.width * scale)),
                              max(1, round(img.height * scale))))
        name = f'{uuid.uuid4().hex}.jpg'
        img.save(staging / name, 'JPEG', quality=88)
        out.append(f'posts/_staging/{name}')
    return jsonify({'photos': out})
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_post_studio_api.py -k photos -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/test_post_studio_api.py
git commit -m "feat(post-studio): POST /api/posts/photos — validate, downscale, stage source photos"
```

---

### Task 6: Rework `POST /api/posts` (save client PNG + `template_json`) and add `GET /api/posts/<id>`

Save now persists what the client produced: the exported **PNG** (multipart file `image`) + the **`template_json`** + the staged photo refs. It no longer renders. Add `GET /api/posts/<id>` returning `template_json` for re-edit, and open it to the mobile read posture. Update the list response.

**Files:**
- Modify: `dental_clinic.py:4778-4815` (`posts_collection` — GET list + POST save)
- Modify: `dental_clinic.py` (add `posts_get` route returning the spec)
- Modify: `dental_clinic.py:2043-2044` (open `GET /api/posts/<id>` to the read posture)
- Modify: `dental_clinic.py:4830-4844` (delete also removes the post's photo dir)
- Test: `tests/test_post_studio_api.py`

**Interfaces:**
- Consumes: `UPLOAD_FOLDER`, the staged paths from Task 5, `read_app_setting` (doctor-name snapshot), `secure_filename`.
- Produces:
  - `POST /api/posts` (multipart: file `image` = exported PNG; form `template_json`; form `theme`, `size`, optional `title`; form `photos` = repeated staged refs) → `200 {'success': True, 'id': N}`; `400` on missing PNG or invalid `template_json`.
  - `GET /api/posts` → list of `{id, title, theme, size, doctor_name, created_at}` (no `photo_count`).
  - `GET /api/posts/<id>` → `{id, title, theme, size, doctor_name, template_json, created_at}` or `404`.

- [ ] **Step 1: Write the failing tests**

Replace the Pillow-era save/preview tests in `tests/test_post_studio_api.py`. First **delete** these now-obsolete tests (engine-dependent): `test_preview_requires_login`, `test_preview_returns_png`, `test_preview_rejects_zero_photos`, `test_preview_rejects_more_than_four_photos`, `test_preview_rejects_bad_theme_and_size`, `_save_one`, `test_save_then_list_serve_delete`, `test_save_render_failure_rolls_back`. Keep `test_readonly_posts_reachable_without_login` and `test_post_writes_still_require_login` (update the latter — preview is gone). Then add:

```python
import json as _json

_TJSON = _json.dumps({'version': 1, 'size': 'square', 'theme': 'dark_premium',
                      'elements': [{'id': 'strip', 'type': 'photoStrip', 'blocks': []}]})


def _save_post(client):
    return client.post(
        '/api/posts',
        data={'image': (io.BytesIO(_png()), 'export.png'),
              'template_json': _TJSON, 'theme': 'dark_premium',
              'size': 'square', 'title': 'Root Canal'},
        content_type='multipart/form-data')


def test_save_requires_login(client):
    assert client.post('/api/posts').status_code == 401


def test_save_persists_png_and_spec_then_roundtrips(client):
    _login(client)
    pid = _save_post(client).get_json()['id']
    # list
    listing = client.get('/api/posts').get_json()
    row = next(p for p in listing if p['id'] == pid)
    assert row['title'] == 'Root Canal'
    assert 'photo_count' not in row
    # get-spec (re-edit) round-trips the template_json
    spec = client.get(f'/api/posts/{pid}').get_json()
    assert _json.loads(spec['template_json'])['theme'] == 'dark_premium'
    # serve the exported PNG
    img = client.get(f'/api/posts/{pid}/image')
    assert img.status_code == 200 and img.content_type.startswith('image/png')
    # delete
    assert client.delete(f'/api/posts/{pid}').status_code == 200
    assert client.get(f'/api/posts/{pid}').status_code == 404


def test_save_rejects_missing_png_or_bad_spec(client):
    _login(client)
    no_png = client.post('/api/posts',
                         data={'template_json': _TJSON, 'theme': 'dark_premium', 'size': 'square'},
                         content_type='multipart/form-data')
    assert no_png.status_code == 400
    bad_spec = client.post('/api/posts',
                           data={'image': (io.BytesIO(_png()), 'e.png'),
                                 'template_json': 'not json', 'theme': 'dark_premium', 'size': 'square'},
                           content_type='multipart/form-data')
    assert bad_spec.status_code == 400


def test_get_spec_open_to_mobile_read_posture(client):
    # like /api/posts and /api/posts/<id>/image, the spec GET is reachable
    # without the portal session (mobile uses device/clinic-token headers).
    assert client.get('/api/posts/999').status_code == 404  # handler ran, not 401
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_post_studio_api.py -v`
Expected: FAIL — new save contract not implemented; `GET /api/posts/<id>` missing/401.

- [ ] **Step 3: Open `GET /api/posts/<id>` to the read posture**

In `dental_clinic.py`, replace:

```python
    if request.method == 'GET' and (path == '/api/posts'
                                    or re.match(r'^/api/posts/\d+/image$', path)):
        return None
```

with:

```python
    if request.method == 'GET' and (path == '/api/posts'
                                    or re.match(r'^/api/posts/\d+(/image)?$', path)):
        return None
```

- [ ] **Step 4: Rework `posts_collection` (GET list + POST save)**

In `dental_clinic.py`, replace the whole `posts_collection` body (the GET list query + the POST save block, `dental_clinic.py:4778-4815`) with:

```python
@app.route('/api/posts', methods=['GET', 'POST'])
def posts_collection():
    import json as _json
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    if request.method == 'GET':
        cur.execute('''SELECT id, title, theme, size, doctor_name, created_at
                       FROM marketing_posts ORDER BY created_at DESC''')
        rows = [{'id': r[0], 'title': r[1], 'theme': r[2], 'size': r[3],
                 'doctor_name': r[4], 'created_at': r[5]} for r in cur.fetchall()]
        conn.close()
        return jsonify(rows)

    # POST: persist the client-exported PNG + the editable spec.
    png = request.files.get('image')
    if not png or not png.filename:
        conn.close()
        return jsonify({'error': 'No exported image'}), 400
    template_json = request.form.get('template_json') or ''
    try:
        _json.loads(template_json)
    except (ValueError, TypeError):
        conn.close()
        return jsonify({'error': 'Invalid template_json'}), 400
    theme = request.form.get('theme') or ''
    size = request.form.get('size') or ''
    title = request.form.get('title') or ''
    doctor = read_app_setting(cur, 'doctor_name', '') or ''

    cur.execute('''INSERT INTO marketing_posts (title, theme, size, doctor_name, template_json)
                   VALUES (?,?,?,?,?)''', (title, theme, size, doctor, template_json))
    new_id = cur.lastrowid
    post_dir = UPLOAD_FOLDER / 'posts' / str(new_id)
    post_dir.mkdir(parents=True, exist_ok=True)
    dest = post_dir / f'{new_id}.png'
    try:
        png.save(str(dest))
        # Move any staged source photos into the post's own dir (best-effort).
        for ref in request.form.getlist('photos'):
            src = UPLOAD_FOLDER / ref
            if str(src).startswith(str(UPLOAD_FOLDER / 'posts' / '_staging')) and src.exists():
                src.replace(post_dir / src.name)
        cur.execute('UPDATE marketing_posts SET file_name=?, file_path=? WHERE id=?',
                    (f'{new_id}.png', str(dest), new_id))
        conn.commit()
    except Exception:  # noqa: BLE001 — never leak the connection or persist a half-written row
        conn.rollback()
        conn.close()
        return jsonify({'error': 'Failed to save the post'}), 500
    conn.close()
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/posts/<int:post_id>', methods=['GET'])
def posts_get(post_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''SELECT id, title, theme, size, doctor_name, template_json, created_at
                   FROM marketing_posts WHERE id=?''', (post_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'id': row[0], 'title': row[1], 'theme': row[2], 'size': row[3],
                    'doctor_name': row[4], 'template_json': row[5], 'created_at': row[6]})
```

- [ ] **Step 5: Make delete remove the post's photo dir**

In `dental_clinic.py`, replace the `posts_delete` body:

```python
@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
def posts_delete(post_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT file_path FROM marketing_posts WHERE id=?', (post_id,))
    row = cur.fetchone()
    if row and row[0]:
        post_dir = Path(row[0]).parent
        if post_dir.name == str(post_id) and post_dir.exists():
            import shutil
            shutil.rmtree(post_dir, ignore_errors=True)
    cur.execute('DELETE FROM marketing_posts WHERE id=?', (post_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})
```

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/test_post_studio_api.py -v`
Expected: PASS (new contract green).

- [ ] **Step 7: Commit**

```bash
git add dental_clinic.py tests/test_post_studio_api.py
git commit -m "feat(post-studio): save client PNG + template_json; GET /api/posts/<id> spec; dir-aware delete"
```

---

### Task 7: Retire the Pillow engine + remove the dead preview path

Delete the server renderer and everything that only existed to feed it: `post_studio.py`, `post_themes.py`, the golden-image tests, the `POST /api/posts/preview` route, `_build_spec_from_request`, and `import post_studio`. Remove the now-orphaned old generator JS in `templates.py` so nothing calls the removed endpoints.

**Files:**
- Delete: `post_studio.py`, `post_themes.py`, `tests/test_post_studio_engine.py`, `tests/golden/post_studio/` (whole dir)
- Modify: `dental_clinic.py` (remove `posts_preview`, `_build_spec_from_request`, `import post_studio`)
- Modify: `templates.py` (remove the dead `psSave`/`psDownload`/`psOnTabOpen` preview-and-form-upload JS that targets the removed endpoints; keep the tab shell + gallery list `psLoadGallery`)
- Modify: `tests/test_post_studio_api.py` (remove any lingering `post_studio` import/usage, e.g. the monkeypatch in the deleted rollback test)

**Interfaces:**
- Consumes: nothing new.
- Produces: a tree with no `post_studio`/`post_themes` modules, no `/api/posts/preview`, no golden tests; `dental_clinic` imports without `post_studio`.

- [ ] **Step 1: Write the guard test**

Add to `tests/test_post_studio_api.py`:

```python
def test_pillow_engine_is_retired():
    import importlib.util
    assert importlib.util.find_spec('post_studio') is None
    assert importlib.util.find_spec('post_themes') is None


def test_preview_route_is_gone(client):
    _login(client)
    assert client.post('/api/posts/preview').status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_post_studio_api.py -k "retired or preview_route" -v`
Expected: FAIL — modules still importable; `/api/posts/preview` still 200/4xx≠404.

- [ ] **Step 3: Delete the engine modules + golden tests**

```bash
git rm post_studio.py post_themes.py tests/test_post_studio_engine.py
git rm -r tests/golden/post_studio
```

- [ ] **Step 4: Remove the preview route, the spec builder, and the import**

In `dental_clinic.py`, delete the entire `_build_spec_from_request` function (`dental_clinic.py:4748-4763` area, the `photos = []` builder through `return spec, None`) and the entire `posts_preview` route:

```python
@app.route('/api/posts/preview', methods=['POST'])
def posts_preview():
    spec, err = _build_spec_from_request()
    if err:
        return jsonify({'error': err}), 400
    img = post_studio.render_post(spec)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')
```

Then remove the `import post_studio` line (search for `import post_studio` — it is a top-level import). Keep `_PILImage` / Pillow imports (still used by Task 5's upload hygiene).

- [ ] **Step 5: Remove the dead old generator JS in `templates.py`**

In `templates.py`, delete the old generator functions that call the removed endpoints — `psSave`, `psDownload`, and the preview-wiring inside `psOnTabOpen` that POSTed to `/api/posts/preview` and form-uploaded photos to `/api/posts`. Keep `psLoadGallery` (it only uses the still-present `GET /api/posts` + `GET /api/posts/<id>/image` + `DELETE`). After deletion, run a `node --check` render sweep to confirm the inline `<script>` still parses (the JS-escaping trap):

```bash
python -c "import templates; open('build/_portal.html','w',encoding='utf-8').write(templates.HTML_TEMPLATE)" 2>/dev/null || python -c "import templates,io; io.open('_portal_check.html','w',encoding='utf-8').write(templates.HTML_TEMPLATE)"
node --check _portal_check.html 2>/dev/null; echo "(if node --check rejects HTML, extract the <script> body and re-check; the point is the JS parses)"
```

> The reliable check used in this repo: `python -c "import templates; print('ok')"` must succeed (no Python SyntaxError from an unbalanced string), and the existing `tests/test_post_studio_ui.py` presence tests must still pass. Removing `psSave`/`psDownload` will break any UI test asserting their presence — update those assertions in this step (search `test_post_studio_ui.py` for `psSave`/`psDownload` and drop or adjust them; the tab shell + gallery tests stay).

- [ ] **Step 6: Run the full Post Studio suite + import check**

Run: `python -m pytest tests/test_post_studio_api.py tests/test_post_studio_ui.py -v`
Then: `python -c "import dental_clinic, templates; print('import ok')"`
Expected: PASS; prints `import ok` (no leftover `post_studio` import error).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(post-studio): retire the Pillow render engine + dead preview path"
```

---

### Task 8: Phase-gate verification (P2a)

**Files:** none (verification only).

- [ ] **Step 1: Full Python suite**

Run: `python -m pytest tests/` then check the exit code (summary suppressed): PowerShell `$LASTEXITCODE`.
Expected: `0`.

- [ ] **Step 2: JS state-model suite**

Run: `node --test tests/js/`
Expected: exit `0`, all composition tests pass.

- [ ] **Step 3: Import + no-engine smoke**

Run: `python -c "import dental_clinic, templates; import importlib.util as u; assert u.find_spec('post_studio') is None; print('ok: engine retired, app imports')"`
Expected: prints `ok…`.

- [ ] **Step 4: Confirm the spike decision is recorded**

Open `docs/superpowers/notes/2026-06-27-rasterizer-spike-decision.md` and confirm it states PASS/FAIL and the chosen P2b export technique. P2b's export task is authored from this decision.

- [ ] **Step 5: (No commit.)** P2a is complete. Author the **P2b** plan (editor bundle + canvas renderer + host adapter + client export + tab wiring + Playwright smoke), seeding its export task from the spike decision and its consumption of `composition.js` from the exact exports in Tasks 3–4.

---

## Self-Review

- **Spec coverage (P2a scope):** client-side rasterizer validated → Task 1; `template_json` data model (add col, drop `photo_count`/`labels_json`) → Task 2; composition state model (default-template construction + serialize round-trip + block ops + badge renumber, node-tested) → Tasks 3–4; endpoints rework (`POST /api/posts/photos`, save PNG+spec, `GET /api/posts/<id>` spec, open-read posture, removed preview) → Tasks 5–6; Pillow engine retirement (`post_studio.py`/`post_themes.py`/golden tests/preview/`_build_spec_from_request`) → Task 7; gates (pytest + node) → Task 8. Deferred to **P2b** (correctly, by dependency): the editor HTML/JS bundle, the canvas renderer, the host adapter + desktop host, the client PNG export *implementation* (gated on Task 1's decision), the tab UI rewire, and the Playwright visual/behavioral smoke. ✓
- **Placeholder scan:** every code step shows exact old/new text, full module bodies, or exact deletions. The only deliberate fill-in is the spike harness's base64 font (Task 1 Step 1 explicitly instructs encoding an existing `fonts/` TTF — a concrete action, not a TODO). The export *implementation* is intentionally not written here because it is spike-gated; that is a sequencing decision, documented, not a placeholder. ✓
- **Type/name consistency:** `composition.js` exports (`MAX_BLOCKS`, `SIZES`, `TEMPLATES`, `defaultComposition`, `serialize`, `deserialize`, `addBlock`, `removeBlock`, `reorderBlock`, `insertBlock`, `renumber`) are defined in Tasks 3–4 and consumed by the same-named test imports; `template_json` column name is identical across Tasks 2, 6, 7; `posts/_staging/` staging prefix is produced in Task 5 and consumed in Task 6's save; `GET /api/posts/<id>` is added in Task 6 and its open-read regex `^/api/posts/\d+(/image)?$` covers both it and the image route. ✓
- **Interim-state honesty:** Task 7 explicitly removes the dead old generator JS so the (temporarily inert) tab calls no removed endpoint; the working editor returns in P2b. Acceptable because P2a–P6 stack on the branch with no interim release. ✓
