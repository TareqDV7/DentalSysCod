# Post Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Post Studio" feature to DentaCare that composes 1–4 clinical photos into a branded, themed social-media image, backed by a reusable clinic-branding identity (doctor name, logo, default theme).

**Architecture:** A pure, Flask-free render module (`post_studio.py` + `post_themes.py`) composes images with Pillow. Thin Flask endpoints in `dental_clinic.py` handle branding CRUD, preview, and a persisted gallery (`marketing_posts` table + files under `UPLOAD_FOLDER/posts/`, which already syncs via the export bundle). Desktop UI lives in `templates.py`/`web_assets.py`; mobile gets a read-only viewer.

**Tech Stack:** Python 3, Flask, Pillow (already a dep), `arabic-reshaper` + `python-bidi` (new), bundled OFL TTF fonts, SQLite, pytest. Frontend: vanilla JS/HTML/CSS in `templates.py`/`web_assets.py`. Mobile: Flutter.

## Global Constraints

- **Shell:** prefix every shell command with `rtk` (e.g. `rtk git commit ...`), per user global CLAUDE.md.
- **Commits:** conventional-commit format; **no `Co-Authored-By` / attribution line** (disabled globally).
- **CSRF:** unsafe-method endpoints are covered by the existing fetch interceptor; tests inherit `conftest.py`'s `_CsrfTestClient` which auto-attaches the token. Do not add CSRF code.
- **Auth:** new endpoints are desktop-only and MUST require login — register them in `_AUTH_REQUIRED_EXACT` (exact paths) and/or `_AUTH_REQUIRED_PREFIXES` (`dental_clinic.py:1986`). API calls without `session['uid']` must return 401.
- **Tests authenticate** by seeding the session: `with client.session_transaction() as sess: sess['uid'] = 1`.
- **Bilingual:** every user-facing string must have EN + AR. Arabic text in posts must be shaped (reshape + bidi) before PIL draws it.
- **`templates.py` JS escaping trap:** `HTML_TEMPLATE`/asset strings are normal Python strings — a literal `'\n'` in injected JS collapses to a real newline and breaks the whole inline script. Double-escape (`'\\n'`) and verify every changed render path with a `node --check` sweep.
- **File size:** keep new modules focused (< ~500 lines each); `post_studio.py` and `post_themes.py` stay separate.
- **Coverage:** ≥ 80% on new Python code; the full `python -m pytest tests/` suite stays green (check `$LASTEXITCODE`; summary is suppressed).
- **Image composition is server-side** (the Flask service binary). Preview == export (same render path).

---

## File Structure

**Create:**
- `post_studio.py` — pure render engine (geometry, cropping, Arabic shaping, `render_post`).
- `post_themes.py` — theme palettes + font path config (data only).
- `fonts/` — bundled OFL TTFs (Latin sans, serif, Arabic).
- `tests/test_post_studio_engine.py` — unit + golden-image tests for the engine.
- `tests/test_branding_api.py` — branding endpoints.
- `tests/test_post_studio_api.py` — preview + gallery endpoints.

**Modify:**
- `dental_clinic.py` — `marketing_posts` table; branding + posts endpoints; auth-set registration.
- `requirements.txt` — add `arabic-reshaper`, `python-bidi`.
- `DentaCare.spec` — add PIL + arabic-reshaper/bidi to **COMMON_HIDDEN** (service binary renders), bundle `fonts/`.
- `templates.py` — Post Studio nav tab + tab content + Settings branding panel + first-run wizard markup.
- `web_assets.py` — Post Studio JS/CSS, branding panel JS, wizard JS.
- `clinic_mobile_app/lib/...` — read-only Posts screen (Phase 5).

**Engine interface (locked here, referenced by all tasks):**
```python
# post_studio.py
from collections import namedtuple
Rect = namedtuple('Rect', 'x y w h')

POST_SIZES = {'square': (1080, 1080), 'portrait': (1080, 1350), 'story': (1080, 1920)}
THEMES = ('dark_premium', 'clean_clinical', 'soft_mint', 'bold_editorial')

@dataclass(frozen=True)
class Photo:
    image: 'PIL.Image.Image'
    label: str = ''

@dataclass(frozen=True)
class PostSpec:
    photos: list          # list[Photo], length 1..4
    doctor_name: str
    theme: str            # one of THEMES
    size: str             # one of POST_SIZES keys
    logo: object = None   # PIL.Image.Image | None

def photo_grid_rects(count: int, region: Rect, gap: int = 16) -> list:  # -> list[Rect]
def fit_crop(image, w: int, h: int):                                    # -> PIL.Image
def is_rtl(text: str) -> bool
def shape_arabic(text: str) -> str
def render_post(spec: PostSpec):                                        # -> PIL.Image (RGB)
```

```python
# post_themes.py
@dataclass(frozen=True)
class Theme:
    key: str
    bg: tuple            # RGB
    fg: tuple
    accent: tuple
    panel: tuple         # photo frame / card color
    heading_font: str    # path under fonts/
    label_font: str
    arabic_font: str
    header_h_frac: float # header height as fraction of canvas height
    footer_h_frac: float

THEMES_BY_KEY: dict       # {key: Theme}
def get_theme(key: str) -> Theme
```

---

## Phase 1 — Branding store & API

### Task 1: Branding GET/PUT endpoint

**Files:**
- Modify: `dental_clinic.py` (add route near the other `/api/` settings routes; register paths in `_AUTH_REQUIRED_EXACT` at `:1986`)
- Test: `tests/test_branding_api.py`

**Interfaces:**
- Consumes: `read_app_setting(cursor, key, default)`, `write_app_setting(cursor, key, value)` (`dental_clinic.py:612,620`).
- Produces: `GET /api/branding` → `{doctor_name, doctor_name_ar, default_theme, has_logo}`; `PUT /api/branding` accepts JSON `{doctor_name, doctor_name_ar, default_theme}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_branding_api.py
import sqlite3
import pytest
import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    db = data_dir / 'dental_clinic.db'
    uploads = data_dir / 'uploads'
    uploads.mkdir()
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', data_dir)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db))
    monkeypatch.setattr(dental_clinic, 'UPLOAD_FOLDER', uploads)
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        yield c


def _login(client):
    with client.session_transaction() as sess:
        sess['uid'] = 1
        sess['uname'] = 'tester'


def test_branding_requires_login(client):
    assert client.get('/api/branding').status_code == 401


def test_branding_round_trips(client):
    _login(client)
    r = client.put('/api/branding', json={
        'doctor_name': 'Dr. Wasfy Barzaq',
        'doctor_name_ar': 'د. وصفي برزق',
        'default_theme': 'dark_premium',
    })
    assert r.status_code == 200
    body = client.get('/api/branding').get_json()
    assert body['doctor_name'] == 'Dr. Wasfy Barzaq'
    assert body['doctor_name_ar'] == 'د. وصفي برزق'
    assert body['default_theme'] == 'dark_premium'
    assert body['has_logo'] is False


def test_branding_rejects_unknown_theme(client):
    _login(client)
    r = client.put('/api/branding', json={'default_theme': 'neon_chaos'})
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk python -m pytest tests/test_branding_api.py -q`
Expected: FAIL (404/401 mismatch — route not defined).

- [ ] **Step 3: Add the endpoint and register auth**

In `dental_clinic.py`, extend the auth set (`:1986`) — add `'/api/branding'` to `_AUTH_REQUIRED_EXACT` and add `'/api/branding/'` to `_AUTH_REQUIRED_PREFIXES` (so the logo sub-route in Task 2 is covered):

```python
_AUTH_REQUIRED_PREFIXES = ('/invoice/', '/api/branding/', '/api/posts/')
```
and add `'/api/branding', '/api/posts'` to the `_AUTH_REQUIRED_EXACT` set literal.

Add the route (place beside other settings routes, e.g. after the `/api/support` block ~`:4653`):

```python
_VALID_POST_THEMES = ('dark_premium', 'clean_clinical', 'soft_mint', 'bold_editorial')


@app.route('/api/branding', methods=['GET', 'PUT'])
def branding():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if request.method == 'GET':
        logo_path = read_app_setting(cursor, 'clinic_logo_path', '')
        out = {
            'doctor_name': read_app_setting(cursor, 'doctor_name', '') or '',
            'doctor_name_ar': read_app_setting(cursor, 'doctor_name_ar', '') or '',
            'default_theme': read_app_setting(cursor, 'post_default_theme', 'clean_clinical'),
            'has_logo': bool(logo_path and Path(logo_path).exists()),
        }
        conn.close()
        return jsonify(out)

    data = request.get_json(silent=True) or {}
    theme = data.get('default_theme')
    if theme is not None and theme not in _VALID_POST_THEMES:
        conn.close()
        return jsonify({'error': 'Unknown theme'}), 400
    for key, col in (('doctor_name', 'doctor_name'),
                     ('doctor_name_ar', 'doctor_name_ar'),
                     ('default_theme', 'post_default_theme')):
        if key in data and data[key] is not None:
            write_app_setting(cursor, col, str(data[key]))
    conn.commit()
    conn.close()
    return jsonify({'success': True})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk python -m pytest tests/test_branding_api.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_branding_api.py
rtk git commit -m "feat(post-studio): branding GET/PUT settings endpoint"
```

---

### Task 2: Branding logo upload + serve

**Files:**
- Modify: `dental_clinic.py` (two routes: `POST /api/branding/logo`, `GET /api/branding/logo`)
- Test: `tests/test_branding_api.py` (extend)

**Interfaces:**
- Consumes: `UPLOAD_FOLDER`, `secure_filename`, Pillow (`from PIL import Image`).
- Produces: logo stored at `UPLOAD_FOLDER/branding/logo.png`; `clinic_logo_path` app_setting; `GET /api/branding/logo` serves the PNG (404 if none).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_branding_api.py
import io
from PIL import Image


def _png_bytes(color=(10, 20, 30), size=(64, 64)):
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, 'PNG')
    return buf.getvalue()


def test_logo_upload_then_serve(client):
    _login(client)
    r = client.post('/api/branding/logo',
                    data={'logo': (io.BytesIO(_png_bytes()), 'logo.png')},
                    content_type='multipart/form-data')
    assert r.status_code == 200
    assert client.get('/api/branding').get_json()['has_logo'] is True
    served = client.get('/api/branding/logo')
    assert served.status_code == 200
    assert Image.open(io.BytesIO(served.data)).size == (64, 64)


def test_logo_upload_rejects_non_image(client):
    _login(client)
    r = client.post('/api/branding/logo',
                    data={'logo': (io.BytesIO(b'not-an-image'), 'evil.png')},
                    content_type='multipart/form-data')
    assert r.status_code == 400


def test_logo_serve_404_when_absent(client):
    _login(client)
    assert client.get('/api/branding/logo').status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk python -m pytest tests/test_branding_api.py -k logo -q`
Expected: FAIL (routes not defined).

- [ ] **Step 3: Implement the routes**

```python
@app.route('/api/branding/logo', methods=['POST'])
def branding_logo_upload():
    file = request.files.get('logo')
    if not file:
        return jsonify({'error': 'No logo uploaded'}), 400
    try:
        img = Image.open(file.stream)
        img.verify()                      # reject non-images
        file.stream.seek(0)
        img = Image.open(file.stream).convert('RGBA')
    except Exception:                     # noqa: BLE001
        return jsonify({'error': 'File is not a valid image'}), 400
    branding_dir = UPLOAD_FOLDER / 'branding'
    branding_dir.mkdir(parents=True, exist_ok=True)
    dest = branding_dir / 'logo.png'
    img.save(dest, 'PNG')
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    write_app_setting(cur, 'clinic_logo_path', str(dest))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/branding/logo', methods=['GET'])
def branding_logo_serve():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    path = read_app_setting(cur, 'clinic_logo_path', '')
    conn.close()
    if not path or not Path(path).exists():
        return jsonify({'error': 'No logo'}), 404
    return send_file(path, mimetype='image/png')
```

Confirm `from PIL import Image` is imported at module top (add if missing).

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk python -m pytest tests/test_branding_api.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_branding_api.py
rtk git commit -m "feat(post-studio): clinic logo upload + serve"
```

---

## Phase 2 — Render engine

### Task 3: Dependencies & font bundling

**Files:**
- Modify: `requirements.txt`, `DentaCare.spec`
- Create: `fonts/` with the TTFs below

- [ ] **Step 1: Add Python deps**

Append to `requirements.txt`:
```
arabic-reshaper>=3.0
python-bidi>=0.4
```
Install: `rtk pip install arabic-reshaper python-bidi`

- [ ] **Step 2: Add OFL fonts**

Download these SIL OFL fonts (Google Fonts) into `fonts/` (exact filenames — the engine references them):
```
fonts/Manrope-Regular.ttf
fonts/Manrope-Bold.ttf
fonts/Manrope-ExtraBold.ttf
fonts/PlayfairDisplay-Bold.ttf
fonts/Cairo-Regular.ttf
fonts/Cairo-Bold.ttf
```
Verify each loads: `rtk python -c "from PIL import ImageFont; ImageFont.truetype('fonts/Manrope-Bold.ttf', 40); print('ok')"`

- [ ] **Step 3: Bundle into the service binary**

In `DentaCare.spec`, the Flask app (which renders) ships as `DentaCareService.exe`, so PIL + the new deps must be in **COMMON_HIDDEN** (not just `window_a`). Add to `COMMON_HIDDEN`:
```python
    'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont', 'PIL.ImageOps',
    'arabic_reshaper', 'bidi', 'bidi.algorithm',
```
Add fonts to `COMMON_DATAS`:
```python
COMMON_DATAS = [
    ('DentaCare.PNG', '.'),
    ('fonts', 'fonts'),
]
```

- [ ] **Step 4: Verify imports resolve**

Run: `rtk python -c "import arabic_reshaper; from bidi.algorithm import get_display; from PIL import Image, ImageDraw, ImageFont, ImageOps; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
rtk git add requirements.txt DentaCare.spec fonts/
rtk git commit -m "chore(post-studio): bundle PIL+arabic deps and OFL fonts into service build"
```

---

### Task 4: `photo_grid_rects` geometry

**Files:**
- Create: `post_studio.py`
- Test: `tests/test_post_studio_engine.py`

**Interfaces:**
- Produces: `Rect = namedtuple('Rect','x y w h')`; `photo_grid_rects(count, region: Rect, gap=16) -> list[Rect]`. Layout: 1=full; 2=two columns; 3=three columns; 4=2×2 grid. Rects tile `region` (minus gaps), stay inside it, never overlap.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_post_studio_engine.py
import pytest
from post_studio import Rect, photo_grid_rects


def _inside(r, region):
    return (r.x >= region.x and r.y >= region.y
            and r.x + r.w <= region.x + region.w + 1
            and r.y + r.h <= region.y + region.h + 1)


@pytest.mark.parametrize('count', [1, 2, 3, 4])
def test_grid_returns_count_rects_inside_region(count):
    region = Rect(0, 100, 1080, 880)
    rects = photo_grid_rects(count, region)
    assert len(rects) == count
    for r in rects:
        assert r.w > 0 and r.h > 0
        assert _inside(r, region)


def test_four_is_two_by_two():
    region = Rect(0, 0, 1000, 1000)
    rects = photo_grid_rects(4, region, gap=0)
    xs = sorted({r.x for r in rects})
    ys = sorted({r.y for r in rects})
    assert len(xs) == 2 and len(ys) == 2


def test_rects_do_not_overlap():
    region = Rect(0, 0, 1080, 900)
    rects = photo_grid_rects(3, region)
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            a, b = rects[i], rects[j]
            sep = (a.x + a.w <= b.x or b.x + b.w <= a.x
                   or a.y + a.h <= b.y or b.y + b.h <= a.y)
            assert sep
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk python -m pytest tests/test_post_studio_engine.py -q`
Expected: FAIL (`No module named 'post_studio'`).

- [ ] **Step 3: Implement geometry**

```python
# post_studio.py
"""Pure, Flask-free post-image composition engine."""
from collections import namedtuple
from dataclasses import dataclass, field

Rect = namedtuple('Rect', 'x y w h')

POST_SIZES = {'square': (1080, 1080), 'portrait': (1080, 1350), 'story': (1080, 1920)}
THEMES = ('dark_premium', 'clean_clinical', 'soft_mint', 'bold_editorial')


def _cols_rows(count):
    return {1: (1, 1), 2: (2, 1), 3: (3, 1), 4: (2, 2)}[count]


def photo_grid_rects(count, region, gap=16):
    if count not in (1, 2, 3, 4):
        raise ValueError('count must be 1..4')
    cols, rows = _cols_rows(count)
    cell_w = (region.w - gap * (cols - 1)) // cols
    cell_h = (region.h - gap * (rows - 1)) // rows
    rects = []
    for i in range(count):
        c, r = i % cols, i // cols
        rects.append(Rect(region.x + c * (cell_w + gap),
                          region.y + r * (cell_h + gap),
                          cell_w, cell_h))
    return rects
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk python -m pytest tests/test_post_studio_engine.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
rtk git add post_studio.py tests/test_post_studio_engine.py
rtk git commit -m "feat(post-studio): adaptive photo grid geometry"
```

---

### Task 5: `fit_crop`, `is_rtl`, `shape_arabic`

**Files:**
- Modify: `post_studio.py`
- Test: `tests/test_post_studio_engine.py` (extend)

**Interfaces:**
- Produces: `fit_crop(image, w, h) -> PIL.Image` (cover/center-crop, exact size); `is_rtl(text) -> bool` (true if any Arabic codepoint); `shape_arabic(text) -> str` (reshape + bidi).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_post_studio_engine.py
from PIL import Image
from post_studio import fit_crop, is_rtl, shape_arabic


def test_fit_crop_exact_size():
    src = Image.new('RGB', (400, 200), (255, 0, 0))
    out = fit_crop(src, 100, 100)
    assert out.size == (100, 100)


def test_is_rtl():
    assert is_rtl('د. وصفي') is True
    assert is_rtl('Dr. Wasfy') is False


def test_shape_arabic_changes_arabic_only():
    assert shape_arabic('Dr. Wasfy') == 'Dr. Wasfy'
    shaped = shape_arabic('عيادة')
    assert isinstance(shaped, str) and shaped != ''
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk python -m pytest tests/test_post_studio_engine.py -k "fit_crop or rtl or arabic" -q`
Expected: FAIL (names not defined).

- [ ] **Step 3: Implement**

```python
# add to post_studio.py
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import ImageOps


def fit_crop(image, w, h):
    return ImageOps.fit(image.convert('RGB'), (w, h), method=Image.LANCZOS)


def is_rtl(text):
    return any('؀' <= ch <= 'ۿ' for ch in (text or ''))


def shape_arabic(text):
    if not is_rtl(text):
        return text
    return get_display(arabic_reshaper.reshape(text))
```
(Add `from PIL import Image` to the imports.)

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk python -m pytest tests/test_post_studio_engine.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
rtk git add post_studio.py tests/test_post_studio_engine.py
rtk git commit -m "feat(post-studio): image cover-crop + Arabic shaping helpers"
```

---

### Task 6: Theme palettes + single-theme `render_post`

**Files:**
- Create: `post_themes.py`
- Modify: `post_studio.py` (`PostSpec`, `Photo`, `render_post`)
- Test: `tests/test_post_studio_engine.py` (extend)

**Interfaces:**
- Consumes: `post_themes.get_theme(key) -> Theme`, `photo_grid_rects`, `fit_crop`, `shape_arabic`.
- Produces: `Photo(image, label='')`, `PostSpec(photos, doctor_name, theme, size, logo=None)`, `render_post(spec) -> PIL.Image` (RGB, exact `POST_SIZES[size]`).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_post_studio_engine.py
from post_studio import Photo, PostSpec, render_post, POST_SIZES


def _spec(theme='clean_clinical', size='square', n=3):
    photos = [Photo(Image.new('RGB', (300, 300), (i * 60, 120, 200)),
                    label=lbl) for i, lbl in zip(range(n), ['Before', 'During', 'After'])]
    return PostSpec(photos=photos, doctor_name='Dr. Wasfy Barzaq',
                    theme=theme, size=size, logo=None)


def test_render_returns_exact_size():
    img = render_post(_spec())
    assert img.size == POST_SIZES['square']
    assert img.mode == 'RGB'


def test_render_is_not_blank():
    img = render_post(_spec())
    assert len(img.getcolors(maxcolors=100000) or [1] * 999) > 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk python -m pytest tests/test_post_studio_engine.py -k render -q`
Expected: FAIL (names not defined).

- [ ] **Step 3: Implement themes + render**

```python
# post_themes.py
from dataclasses import dataclass

_F = 'fonts/'


@dataclass(frozen=True)
class Theme:
    key: str
    bg: tuple
    fg: tuple
    accent: tuple
    panel: tuple
    heading_font: str
    label_font: str
    arabic_font: str
    header_h_frac: float = 0.16
    footer_h_frac: float = 0.06


THEMES_BY_KEY = {
    'dark_premium': Theme('dark_premium', (22, 22, 26), (245, 240, 230), (201, 162, 39),
                          (32, 32, 38), _F + 'PlayfairDisplay-Bold.ttf',
                          _F + 'Manrope-Bold.ttf', _F + 'Cairo-Bold.ttf'),
    'clean_clinical': Theme('clean_clinical', (255, 255, 255), (24, 33, 54), (56, 189, 248),
                            (238, 244, 250), _F + 'Manrope-ExtraBold.ttf',
                            _F + 'Manrope-Bold.ttf', _F + 'Cairo-Bold.ttf'),
    'soft_mint': Theme('soft_mint', (228, 246, 240), (18, 60, 52), (45, 178, 148),
                       (255, 255, 255), _F + 'Manrope-ExtraBold.ttf',
                       _F + 'Manrope-Bold.ttf', _F + 'Cairo-Bold.ttf'),
    'bold_editorial': Theme('bold_editorial', (250, 240, 0), (10, 10, 10), (10, 10, 10),
                            (255, 255, 255), _F + 'Manrope-ExtraBold.ttf',
                            _F + 'Manrope-ExtraBold.ttf', _F + 'Cairo-Bold.ttf',
                            header_h_frac=0.18),
}


def get_theme(key):
    return THEMES_BY_KEY.get(key, THEMES_BY_KEY['clean_clinical'])
```

```python
# add to post_studio.py
from PIL import ImageDraw, ImageFont
from post_themes import get_theme


@dataclass(frozen=True)
class Photo:
    image: object
    label: str = ''


@dataclass(frozen=True)
class PostSpec:
    photos: list
    doctor_name: str
    theme: str
    size: str
    logo: object = None


def _font(path, px):
    return ImageFont.truetype(path, px)


def _draw_text(draw, xy, text, font, fill, anchor='la'):
    draw.text(xy, shape_arabic(text), font=font, fill=fill, anchor=anchor)


def render_post(spec):
    if not (1 <= len(spec.photos) <= 4):
        raise ValueError('photos must be 1..4')
    if spec.size not in POST_SIZES:
        raise ValueError('bad size')
    W, H = POST_SIZES[spec.size]
    theme = get_theme(spec.theme)
    canvas = Image.new('RGB', (W, H), theme.bg)
    draw = ImageDraw.Draw(canvas)

    header_h = int(H * theme.header_h_frac)
    footer_h = int(H * theme.footer_h_frac)
    pad = int(W * 0.04)

    # Header: doctor name (+ logo at right if present)
    name_font = _font(theme.heading_font, int(header_h * 0.42))
    _draw_text(draw, (pad, header_h // 2), spec.doctor_name, name_font,
               theme.fg, anchor='lm')
    if spec.logo is not None:
        lh = int(header_h * 0.66)
        logo = fit_crop(spec.logo.convert('RGB'), lh, lh)
        canvas.paste(logo, (W - pad - lh, (header_h - lh) // 2))

    # Photo grid
    region = Rect(pad, header_h, W - 2 * pad, H - header_h - footer_h - pad)
    rects = photo_grid_rects(len(spec.photos), region)
    label_font = _font(theme.label_font, max(20, int(region.h * 0.045)))
    for ph, r in zip(spec.photos, rects):
        canvas.paste(fit_crop(ph.image, r.w, r.h), (r.x, r.y))
        if ph.label:
            draw.rectangle([r.x, r.y + r.h - 44, r.x + r.w, r.y + r.h],
                           fill=theme.accent)
            _draw_text(draw, (r.x + r.w // 2, r.y + r.h - 22), ph.label,
                       label_font, theme.bg, anchor='mm')

    # Footer accent bar
    draw.rectangle([0, H - footer_h, W, H], fill=theme.accent)
    return canvas
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk python -m pytest tests/test_post_studio_engine.py -q`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
rtk git add post_studio.py post_themes.py tests/test_post_studio_engine.py
rtk git commit -m "feat(post-studio): theme palettes + render_post composition"
```

---

### Task 7: All themes × sizes + golden-image coverage

**Files:**
- Modify: `tests/test_post_studio_engine.py`
- Create: `tests/golden/post_studio/*.png` (committed references)

**Interfaces:**
- Consumes: `render_post`, `THEMES`, `POST_SIZES`.

- [ ] **Step 1: Write the matrix + golden test**

```python
# append to tests/test_post_studio_engine.py
import os
from post_studio import THEMES

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), 'golden', 'post_studio')


@pytest.mark.parametrize('theme', THEMES)
@pytest.mark.parametrize('size', list(POST_SIZES))
def test_every_theme_size_renders_correct_dims(theme, size):
    img = render_post(_spec(theme=theme, size=size))
    assert img.size == POST_SIZES[size]


def _diff_ratio(a, b):
    pa, pb = a.tobytes(), b.tobytes()
    if len(pa) != len(pb):
        return 1.0
    diff = sum(1 for x, y in zip(pa, pb) if abs(x - y) > 8)
    return diff / max(1, len(pa))


@pytest.mark.parametrize('theme', THEMES)
def test_golden_square(theme):
    img = render_post(_spec(theme=theme, size='square'))
    path = os.path.join(GOLDEN_DIR, f'{theme}_square.png')
    if not os.path.exists(img and path):  # regenerate locally when missing
        os.makedirs(GOLDEN_DIR, exist_ok=True)
        img.save(path)
        pytest.skip(f'generated golden {path}; re-run to assert')
    assert _diff_ratio(img, Image.open(path).convert('RGB')) < 0.02
```

- [ ] **Step 2: Generate goldens, then assert**

Run twice:
`rtk python -m pytest tests/test_post_studio_engine.py -k golden -q` (1st: generates+skips)
`rtk python -m pytest tests/test_post_studio_engine.py -k golden -q` (2nd: asserts)
Expected: 2nd run PASS. Eyeball the 4 generated PNGs once to confirm they look right before committing.

- [ ] **Step 3: Run full engine suite**

Run: `rtk python -m pytest tests/test_post_studio_engine.py -q`
Expected: PASS (all matrix + golden tests).

- [ ] **Step 4: Commit**

```bash
rtk git add tests/test_post_studio_engine.py tests/golden/post_studio/
rtk git commit -m "test(post-studio): theme×size matrix + golden-image references"
```

---

## Phase 3 — Posts API, generator UI, gallery

### Task 8: `marketing_posts` table + preview endpoint

**Files:**
- Modify: `dental_clinic.py` (table in `init_database`; `POST /api/posts/preview`)
- Test: `tests/test_post_studio_api.py`

**Interfaces:**
- Consumes: `post_studio.render_post`, `Photo`, `PostSpec`; `read_app_setting`.
- Produces: `POST /api/posts/preview` (multipart: `photo` files repeated, `labels` repeated, `doctor_name`, `theme`, `size`) → `image/png` bytes (not saved). Helper `_build_spec_from_request()` reused by Task 9.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_post_studio_api.py
import io
import pytest
from PIL import Image
import dental_clinic


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / 'data'; data_dir.mkdir()
    uploads = data_dir / 'uploads'; uploads.mkdir()
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', data_dir)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(data_dir / 'dental_clinic.db'))
    monkeypatch.setattr(dental_clinic, 'UPLOAD_FOLDER', uploads)
    dental_clinic.init_database()
    dental_clinic.app.config['TESTING'] = True
    with dental_clinic.app.test_client() as c:
        yield c


def _login(client):
    with client.session_transaction() as sess:
        sess['uid'] = 1


def _png(color=(120, 80, 200)):
    b = io.BytesIO(); Image.new('RGB', (200, 200), color).save(b, 'PNG'); return b.getvalue()


def _form(n=2):
    data = {'doctor_name': 'Dr. Wasfy', 'theme': 'clean_clinical', 'size': 'square'}
    files = [('photo', (io.BytesIO(_png()), f'p{i}.png')) for i in range(n)]
    labels = [('labels', lbl) for lbl in ['Before', 'After'][:n]]
    return data, files, labels


def test_preview_requires_login(client):
    assert client.post('/api/posts/preview').status_code == 401


def test_preview_returns_png(client):
    _login(client)
    data, files, labels = _form()
    r = client.post('/api/posts/preview',
                    data={**data, 'photo': [f[1] for f in files],
                          'labels': [l[1] for l in labels]},
                    content_type='multipart/form-data')
    assert r.status_code == 200
    assert r.content_type.startswith('image/png')
    assert Image.open(io.BytesIO(r.data)).size == (1080, 1080)


def test_preview_rejects_zero_photos(client):
    _login(client)
    r = client.post('/api/posts/preview',
                    data={'doctor_name': 'X', 'theme': 'clean_clinical', 'size': 'square'},
                    content_type='multipart/form-data')
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk python -m pytest tests/test_post_studio_api.py -q`
Expected: FAIL.

- [ ] **Step 3: Add table + endpoint**

In `init_database()` add (near other `CREATE TABLE` calls):
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

Add helper + route:
```python
import post_studio
from PIL import Image as _PILImage

_VALID_POST_SIZES = ('square', 'portrait', 'story')


def _build_spec_from_request():
    files = request.files.getlist('photo')
    if not files or len(files) > 4:
        return None, 'Add 1 to 4 photos'
    labels = request.form.getlist('labels')
    theme = request.form.get('theme', 'clean_clinical')
    size = request.form.get('size', 'square')
    if theme not in _VALID_POST_THEMES or size not in _VALID_POST_SIZES:
        return None, 'Bad theme or size'
    photos = []
    for i, f in enumerate(files):
        try:
            img = _PILImage.open(f.stream).convert('RGB')
            img.load()
        except Exception:  # noqa: BLE001
            return None, 'One of the photos is not a valid image'
        photos.append(post_studio.Photo(img, labels[i] if i < len(labels) else ''))
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    logo_path = read_app_setting(cur, 'clinic_logo_path', '')
    doctor = request.form.get('doctor_name') or read_app_setting(cur, 'doctor_name', '') or ''
    conn.close()
    logo = _PILImage.open(logo_path) if logo_path and Path(logo_path).exists() else None
    spec = post_studio.PostSpec(photos=photos, doctor_name=doctor,
                                theme=theme, size=size, logo=logo)
    return spec, None


@app.route('/api/posts/preview', methods=['POST'])
def posts_preview():
    spec, err = _build_spec_from_request()
    if err:
        return jsonify({'error': err}), 400
    img = post_studio.render_post(spec)
    buf = io.BytesIO(); img.save(buf, 'PNG'); buf.seek(0)
    return send_file(buf, mimetype='image/png')
```
(Ensure `import io` is present at module top.)

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk python -m pytest tests/test_post_studio_api.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_post_studio_api.py
rtk git commit -m "feat(post-studio): marketing_posts table + live preview endpoint"
```

---

### Task 9: Save / list / serve / delete gallery

**Files:**
- Modify: `dental_clinic.py`
- Test: `tests/test_post_studio_api.py` (extend)

**Interfaces:**
- Consumes: `_build_spec_from_request`, `post_studio.render_post`, `UPLOAD_FOLDER`.
- Produces: `POST /api/posts` → `{id}` (renders + saves PNG to `UPLOAD_FOLDER/posts/<id>.png` + row); `GET /api/posts` → `[{id,theme,size,doctor_name,photo_count,created_at}]`; `GET /api/posts/<id>/image` → PNG; `DELETE /api/posts/<id>` → `{success}`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_post_studio_api.py
def _save_one(client):
    return client.post('/api/posts',
                       data={'doctor_name': 'Dr. Wasfy', 'theme': 'soft_mint',
                             'size': 'portrait', 'photo': [(io.BytesIO(_png()), 'a.png')],
                             'labels': ['Before']},
                       content_type='multipart/form-data')


def test_save_then_list_serve_delete(client):
    _login(client)
    pid = _save_one(client).get_json()['id']
    listing = client.get('/api/posts').get_json()
    assert any(p['id'] == pid for p in listing)
    img = client.get(f'/api/posts/{pid}/image')
    assert img.status_code == 200 and img.content_type.startswith('image/png')
    assert Image.open(io.BytesIO(img.data)).size == (1080, 1350)
    assert client.delete(f'/api/posts/{pid}').status_code == 200
    assert client.get(f'/api/posts/{pid}/image').status_code == 404


def test_list_requires_login(client):
    assert client.get('/api/posts').status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk python -m pytest tests/test_post_studio_api.py -k "save_then or list_requires" -q`
Expected: FAIL.

- [ ] **Step 3: Implement the routes**

```python
@app.route('/api/posts', methods=['GET', 'POST'])
def posts_collection():
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    if request.method == 'GET':
        cur.execute('''SELECT id, theme, size, doctor_name, photo_count, created_at
                       FROM marketing_posts ORDER BY created_at DESC''')
        rows = [{'id': r[0], 'theme': r[1], 'size': r[2], 'doctor_name': r[3],
                 'photo_count': r[4], 'created_at': r[5]} for r in cur.fetchall()]
        conn.close()
        return jsonify(rows)

    spec, err = _build_spec_from_request()
    if err:
        conn.close()
        return jsonify({'error': err}), 400
    import json as _json
    labels = [p.label for p in spec.photos]
    cur.execute('''INSERT INTO marketing_posts
                   (theme, size, doctor_name, photo_count, labels_json)
                   VALUES (?,?,?,?,?)''',
                (spec.theme, spec.size, spec.doctor_name, len(spec.photos),
                 _json.dumps(labels, ensure_ascii=False)))
    new_id = cur.lastrowid
    posts_dir = UPLOAD_FOLDER / 'posts'; posts_dir.mkdir(parents=True, exist_ok=True)
    dest = posts_dir / f'{new_id}.png'
    post_studio.render_post(spec).save(dest, 'PNG')
    cur.execute('UPDATE marketing_posts SET file_name=?, file_path=? WHERE id=?',
                (f'{new_id}.png', str(dest), new_id))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/posts/<int:post_id>/image')
def posts_image(post_id):
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    cur.execute('SELECT file_path FROM marketing_posts WHERE id=?', (post_id,))
    row = cur.fetchone(); conn.close()
    if not row or not row[0] or not Path(row[0]).exists():
        return jsonify({'error': 'Not found'}), 404
    return send_file(row[0], mimetype='image/png')


@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
def posts_delete(post_id):
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    cur.execute('SELECT file_path FROM marketing_posts WHERE id=?', (post_id,))
    row = cur.fetchone()
    if row and row[0] and Path(row[0]).exists():
        try:
            Path(row[0]).unlink()
        except OSError:
            pass
    cur.execute('DELETE FROM marketing_posts WHERE id=?', (post_id,))
    conn.commit(); conn.close()
    return jsonify({'success': True})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk python -m pytest tests/test_post_studio_api.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the full suite**

Run: `rtk python -m pytest tests/ -q` then check `$LASTEXITCODE` is 0.

- [ ] **Step 6: Commit**

```bash
rtk git add dental_clinic.py tests/test_post_studio_api.py
rtk git commit -m "feat(post-studio): persisted gallery (save/list/serve/delete)"
```

---

### Task 10: Post Studio generator tab (desktop UI)

**Files:**
- Modify: `templates.py` (nav tab + tab panel), `web_assets.py` (JS + CSS)

**Interfaces:**
- Consumes endpoints: `GET /api/branding`, `POST /api/posts/preview`, `POST /api/posts`.
- UI pattern to mirror: nav button at `templates.py:2204-2234`, `switchTab(name, btn)` at `:4683`. Add a `<button class="nav-tab" data-tab="poststudio" onclick="switchTab('poststudio', this)">` and a `<div id="poststudio" class="tab-content">…</div>` sibling of the other tab panels.

- [ ] **Step 1: Add the nav tab + panel markup (EN/AR)**

In `templates.py`, after the `support` nav button (`:2234`) add the Post Studio nav button (use an existing icon sprite id). Add the panel near the other `tab-content` panels with: a photo dropzone/file input (`accept="image/*" multiple`, cap 4), per-photo label inputs (default Before/During/After), a doctor-name input (prefilled from `/api/branding`), a theme `<select>` (4 options), a size `<select>` (square/portrait/story), a `<img id="psPreview">`, and **Save to Gallery** / **Download** buttons. Mirror the bilingual data-i18n approach used by neighboring panels.

- [ ] **Step 2: Add JS (debounced preview + save + download)**

In `web_assets.py`, add a `PostStudio` module. Key behaviors (watch the **JS escaping trap** — use `'\\n'` not `'\n'`):
```javascript
// pseudostructure — follow existing fetch/i18n conventions in web_assets.py
const PS = { photos: [], theme: 'clean_clinical', size: 'square', doctor: '' };
function psBuildForm() {
  const fd = new FormData();
  fd.append('doctor_name', psDoctorInput.value);
  fd.append('theme', PS.theme); fd.append('size', PS.size);
  PS.photos.forEach(p => { fd.append('photo', p.file); fd.append('labels', p.label); });
  return fd;
}
const psRenderPreview = debounce(async () => {
  if (!PS.photos.length) return;
  const r = await fetch('/api/posts/preview', { method: 'POST', body: psBuildForm() });
  if (r.ok) psPreview.src = URL.createObjectURL(await r.blob());
}, 250);
async function psSave() {
  const r = await fetch('/api/posts', { method: 'POST', body: psBuildForm() });
  if (r.ok) { showToast(t('post_saved')); psLoadGallery(); }
}
function psDownload() {  // download current preview blob
  const a = document.createElement('a'); a.href = psPreview.src;
  a.download = 'post.png'; a.click();
}
```
On tab open, `GET /api/branding` to prefill doctor + default theme. Re-render preview on any change (photos/labels/theme/size).

- [ ] **Step 3: Verify the render path (JS escaping sweep)**

Run a `node --check` sweep over the rendered template (per the repo's templates JS-escaping recipe) to ensure no inline-script breakage. Then boot the app and confirm the tab loads with no console errors.

- [ ] **Step 4: Playwright behavioral smoke**

With a seeded active license + login (see repo web-visual-smoke recipe), open Post Studio, attach 2 images, confirm the preview `<img>` gets a blob src, click Save, confirm a gallery item appears. Screenshot light + dark.

- [ ] **Step 5: Commit**

```bash
rtk git add templates.py web_assets.py
rtk git commit -m "feat(post-studio): generator tab with live preview + save/download"
```

---

### Task 11: Gallery view (desktop UI)

**Files:**
- Modify: `templates.py` (gallery sub-panel within the Post Studio tab), `web_assets.py` (gallery JS)

**Interfaces:**
- Consumes: `GET /api/posts`, `GET /api/posts/<id>/image`, `DELETE /api/posts/<id>`.

- [ ] **Step 1: Add gallery markup + JS**

A grid under the generator showing each saved post as a thumbnail (`<img src="/api/posts/{id}/image">`) with **Download** and **Delete** actions. `psLoadGallery()` fetches `/api/posts` and renders cards; Delete calls `DELETE` then reloads (use the existing destructive-action `showConfirm` modal).

- [ ] **Step 2: Verify**

`node --check` sweep; boot app; create a post, confirm it appears in the gallery, download works, delete (via confirm modal) removes it.

- [ ] **Step 3: Commit**

```bash
rtk git add templates.py web_assets.py
rtk git commit -m "feat(post-studio): saved-posts gallery with download/delete"
```

---

## Phase 4 — Branding wizard + Settings panel

### Task 12: Settings → Branding panel

**Files:**
- Modify: `templates.py` (Settings → Account/Data area), `web_assets.py`

**Interfaces:**
- Consumes: `GET/PUT /api/branding`, `POST /api/branding/logo`, `GET /api/branding/logo`.

- [ ] **Step 1: Add a Branding card in Settings**

Fields: doctor name (EN), doctor name (AR), default theme `<select>`, logo upload (`<input type="file" accept="image/*">` + preview of `/api/branding/logo`). Save calls `PUT /api/branding`; logo upload posts to `/api/branding/logo` then refreshes the preview. Bilingual labels.

- [ ] **Step 2: Verify**

`node --check` sweep; boot app; set name/logo/theme, reload, confirm persistence; confirm the Post Studio tab picks up the new defaults.

- [ ] **Step 3: Commit**

```bash
rtk git add templates.py web_assets.py
rtk git commit -m "feat(post-studio): Settings branding panel (name/logo/theme)"
```

---

### Task 13: First-run branding wizard

**Files:**
- Modify: `templates.py` (wizard modal), `web_assets.py` (wizard flow), `dental_clinic.py` (one-time flag via `branding_wizard_done` app_setting; expose in `/api/branding` GET as `wizard_done`)

**Interfaces:**
- Consumes: `GET/PUT /api/branding`, `POST /api/branding/logo`.
- Produces: `branding_wizard_done` flag set when finished/skipped.

- [ ] **Step 1: Add `wizard_done` to branding GET + a setter**

Extend `GET /api/branding` to include `'wizard_done': read_app_setting(cur, 'branding_wizard_done', '') == '1'`. Add a tiny `POST /api/branding/wizard-done` that sets it (covered by `/api/branding/` prefix auth). Add a test in `tests/test_branding_api.py` asserting the flag flips.

- [ ] **Step 2: Add the wizard modal + flow**

After login, if `wizard_done` is false, show a 3-step modal: (1) doctor name EN/AR → (2) logo upload → (3) default theme + finish. "Skip" and "Finish" both call `wizard-done`. Reuse the existing modal primitive.

- [ ] **Step 3: Verify**

`node --check` sweep; fresh temp DB → login → wizard appears; complete it → reload → does not reappear; values land in Settings.

- [ ] **Step 4: Commit**

```bash
rtk git add dental_clinic.py templates.py web_assets.py tests/test_branding_api.py
rtk git commit -m "feat(post-studio): first-run branding wizard"
```

---

## Phase 5 — Mobile read-only viewer

### Task 14: Flutter Posts screen (read-only)

**Files:**
- Create/Modify: `clinic_mobile_app/lib/` (a `posts` screen + service call + nav entry)

**Interfaces:**
- Consumes (via the local server it already syncs with): `GET /api/posts`, `GET /api/posts/<id>/image`.

- [ ] **Step 1: Add a read-only Posts screen**

List synced posts from `GET /api/posts`; tap → full image from `/api/posts/<id>/image`; an OS **share** action (share the downloaded bytes). No create/edit. Bilingual strings via the existing `AppStrings` catalog. Follow the existing screen/service patterns.

- [ ] **Step 2: Verify**

Run `rtk dart analyze` (clean) and `rtk flutter test` (green). Manual: generate a post on desktop, sync, confirm it appears and shares on device.

- [ ] **Step 3: Commit**

```bash
rtk git add clinic_mobile_app/
rtk git commit -m "feat(post-studio): mobile read-only posts viewer"
```

---

## Final verification (before PR)

- [ ] `rtk python -m pytest tests/ -q` → `$LASTEXITCODE` == 0; new code ≥ 80% (`rtk python -m pytest tests/test_post_studio_engine.py tests/test_post_studio_api.py tests/test_branding_api.py --cov=post_studio --cov=post_themes --cov-report=term-missing`).
- [ ] `node --check` render sweep clean; app boots with no console errors (light + dark, EN + AR).
- [ ] `rtk dart analyze` clean; `rtk flutter test` green.
- [ ] Update `README.md` and `CHANGELOG.md` for the Post Studio feature.
- [ ] Rebuild the exe (`rebuild.bat`) and boot-verify a generated post in the packaged service binary (confirms PIL + fonts bundled).
- [ ] Open PR `feat/post-studio` → `main` with test plan.

## Self-Review (completed at write time)

- **Spec coverage:** branding store + wizard + Settings (Tasks 1–2, 12–13) ✓; 4 themes × 3 sizes engine (Tasks 4–7) ✓; flexible 1–4 photos w/ labels (Task 4, 8) ✓; doctor name + logo + B/D/A labels on post (Task 6) ✓; gallery + sync (Task 9, files under `UPLOAD_FOLDER` already in the bundle) ✓; mobile read-only (Task 14) ✓; desktop-only auth + CSRF (Global Constraints, Task 1) ✓.
- **Placeholder scan:** no TBD/TODO; every code step carries real code.
- **Type consistency:** `Rect`, `Photo`, `PostSpec`, `render_post`, `photo_grid_rects`, `fit_crop`, `shape_arabic`, `get_theme`, `_build_spec_from_request` names match across tasks.
- **Note:** UI tasks (10–13) and mobile (14) give concrete anchors + representative code rather than every line, because they edit very large existing files (`templates.py` 521KB, `web_assets.py` 259KB) — execute them by following the cited existing patterns. Backend tasks (1–9) are fully specified and the testable core.
