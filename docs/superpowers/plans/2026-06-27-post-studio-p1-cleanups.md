# Post Studio Redesign — Phase 1 (Cleanups) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the three immediate Post Studio cleanups — a proper tab icon, full removal of the clinic logo, and removal of the first-run branding wizard — without breaking the existing (soon-to-be-replaced) generator.

**Architecture:** Pure subtractive changes plus one icon addition. No new architecture. The existing server-side Pillow generator keeps working after this phase; it is retired later in P2. Branding shrinks to *doctor name (EN/AR) + default theme*, edited only in Settings.

**Tech Stack:** Flask (`dental_clinic.py`), the single-string `HTML_TEMPLATE` (`templates.py`), the inline Phosphor `ICON_SPRITE` (`web_assets.py`), pytest.

## Global Constraints

- **No CDN / no remote assets** — all icons/fonts inlined or bundled (project rule).
- **EN/AR throughout, RTL-aware** — every user-facing string has `en:` and `ar:` keys.
- **Do not change themes in P1** — the four theme keys stay exactly
  `dark_premium`, `clean_clinical`, `soft_mint`, `bold_editorial` (P3 reworks them).
- **`HTML_TEMPLATE` is a normal Python string** — a JS `'\n'` becomes a real newline and breaks the whole inline `<script>`. Double-escape (`'\\n'`) and keep edits balanced.
- **`ICON_SPRITE` is inlined** into `HTML_TEMPLATE` at `templates.py:9746` (`HTML_TEMPLATE.replace("<!--__ICON_SPRITE__-->", ICON_SPRITE)`), so tests asserting on `HTML_TEMPLATE` see the sprite symbols.
- **Reports tab also uses `#i-chart-bar`** (`templates.py:2225`) — leave it untouched; only the Post Studio button (`:2239`) changes.
- **Commits:** conventional-commit messages, no attribution footer (repo setting).
- **Gate:** `python -m pytest tests/` exits 0 (pytest summary is suppressed in this repo — check the exit code).

## Phase roadmap (context)

This plan covers **P1 only**. P2–P6 each get their own plan authored when we reach them, because their exact signatures depend on the real code P2 produces (the WYSIWYG editor module, the composition model, the rasterizer-spike outcome). Spec: `docs/superpowers/specs/2026-06-27-post-studio-redesign.md`.

- **P1 (this plan):** icon · remove logo · remove first-run wizard.
- P2: editor core (host-agnostic) + client PNG export + retire Pillow engine.
- P3: 4 premium themes + 4 starter templates + fonts.
- P4: deep customization (drag, type controls, badges, phases).
- P5: desktop QA & polish.
- P6: mobile editor parity (Flutter WebView).

---

### Task 1: Repoint the Post Studio tab icon to a new `i-image` glyph

The Post Studio tab reuses `#i-chart-bar` (a bar chart). Add a Phosphor **Image** symbol to the sprite and point only the Post Studio button at it.

**Files:**
- Modify: `web_assets.py:3` (add `'image'` to `ICON_NAMES`)
- Modify: `web_assets.py:7` (add the `i-image` `<symbol>` to `ICON_SPRITE`)
- Modify: `templates.py:2238-2240` (repoint the Post Studio button)
- Test: `tests/test_post_studio_ui.py`

**Interfaces:**
- Consumes: the existing sprite format `<symbol id="i-NAME" viewBox="0 0 256 256"><path d="…"/></symbol>`.
- Produces: a sprite symbol with `id="i-image"`; the Post Studio nav button referencing `#i-image`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_post_studio_ui.py`:

```python
def test_post_studio_tab_uses_image_icon():
    # The sprite must define the image glyph...
    assert '<symbol id="i-image"' in HTML_TEMPLATE
    # ...and the Post Studio nav button must use it, not the chart-bar.
    start = HTML_TEMPLATE.index('data-tab="poststudio"')
    button = HTML_TEMPLATE[start:HTML_TEMPLATE.index('</button>', start)]
    assert '#i-image' in button
    assert '#i-chart-bar' not in button
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_post_studio_ui.py::test_post_studio_tab_uses_image_icon -v`
Expected: FAIL — `'<symbol id="i-image"'` is not present.

- [ ] **Step 3: Add the `i-image` symbol to the sprite**

In `web_assets.py`, find the end of the `i-folders` symbol inside `ICON_SPRITE` and append the new symbol immediately after it. Replace:

```
H72V56h45.33L147.2,78.4A8,8,0,0,0,152,80h72Z"/></symbol>
```

with (single line — keep it on one line like the rest of the sprite):

```
H72V56h45.33L147.2,78.4A8,8,0,0,0,152,80h72Z"/></symbol><symbol id="i-image" viewBox="0 0 256 256"><path d="M216,40H40A16,16,0,0,0,24,56V200a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V56A16,16,0,0,0,216,40Zm0,16V158.75l-26.07-26.06a16,16,0,0,0-22.63,0l-20,20-44-44a16,16,0,0,0-22.62,0L40,149.37V56ZM40,172l52-52,80,80H40Zm176,28H194.63l-36-36,20-20L216,181.38V200Zm-72-100a12,12,0,1,1,12,12A12,12,0,0,1,144,100Z"/></symbol>
```

Then add `'image'` to `ICON_NAMES` (line 3) for consistency — replace:

```python
ICON_NAMES = ('house', 'users', 'calendar-dots', 'receipt', 'gear', 'magnifying-glass', 'bell', 'caret-down', 'moon', 'sun', 'sign-out', 'user', 'user-plus', 'chart-bar', 'folders')
```

with:

```python
ICON_NAMES = ('house', 'users', 'calendar-dots', 'receipt', 'gear', 'magnifying-glass', 'bell', 'caret-down', 'moon', 'sun', 'sign-out', 'user', 'user-plus', 'chart-bar', 'folders', 'image')
```

- [ ] **Step 4: Repoint the Post Studio button**

In `templates.py`, replace (this exact 2-line block — unique to the `poststudio` button):

```html
            <button class="nav-tab" data-tab="poststudio" onclick="switchTab('poststudio', this)">
                <span class="tab-icon"><svg class="ic"><use href="#i-chart-bar"/></svg></span>
```

with:

```html
            <button class="nav-tab" data-tab="poststudio" onclick="switchTab('poststudio', this)">
                <span class="tab-icon"><svg class="ic"><use href="#i-image"/></svg></span>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_post_studio_ui.py::test_post_studio_tab_uses_image_icon -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web_assets.py templates.py tests/test_post_studio_ui.py
git commit -m "feat(post-studio): give the tab a proper image icon (not a bar chart)"
```

---

### Task 2: Remove the clinic logo from the backend

Delete the logo upload/serve endpoints, drop `has_logo` from `GET /api/branding`, and stop applying a logo when building a post spec. Leave `post_studio.PostSpec.logo` and the engine's logo block alone — that whole module is deleted in P2, so churning its golden tests now is wasted work.

**Files:**
- Modify: `dental_clinic.py:4709-4737` (branding GET — drop `logo_path` + `has_logo`)
- Modify: `dental_clinic.py:4740-4772` (delete both `/api/branding/logo` routes)
- Modify: `dental_clinic.py:4805-4813` (`_build_spec_from_request` — stop reading/passing a logo)
- Test: `tests/test_post_studio_api.py`

**Interfaces:**
- Consumes: existing `client`/`_login` fixtures in `tests/test_post_studio_api.py`.
- Produces: no `/api/branding/logo` route; `GET /api/branding` JSON without a `has_logo` key.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_post_studio_api.py`:

```python
def test_branding_logo_endpoints_are_gone(client):
    _login(client)
    assert client.post('/api/branding/logo').status_code == 404
    assert client.get('/api/branding/logo').status_code == 404


def test_branding_get_has_no_logo_field(client):
    _login(client)
    body = client.get('/api/branding').get_json()
    assert body is not None
    assert 'has_logo' not in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_post_studio_api.py::test_branding_logo_endpoints_are_gone tests/test_post_studio_api.py::test_branding_get_has_no_logo_field -v`
Expected: FAIL — routes still exist (return 200/4xx≠404) and `has_logo` is present.

- [ ] **Step 3: Drop logo from the branding GET**

In `dental_clinic.py`, replace:

```python
    if request.method == 'GET':
        logo_path = read_app_setting(cursor, 'clinic_logo_path', '')
        out = {
            'doctor_name': read_app_setting(cursor, 'doctor_name', '') or '',
            'doctor_name_ar': read_app_setting(cursor, 'doctor_name_ar', '') or '',
            'default_theme': read_app_setting(cursor, 'post_default_theme', 'clean_clinical'),
            'has_logo': bool(logo_path and Path(logo_path).exists()),
            'wizard_done': read_app_setting(cursor, 'branding_wizard_done', '') == '1',
        }
        conn.close()
        return jsonify(out)
```

with:

```python
    if request.method == 'GET':
        out = {
            'doctor_name': read_app_setting(cursor, 'doctor_name', '') or '',
            'doctor_name_ar': read_app_setting(cursor, 'doctor_name_ar', '') or '',
            'default_theme': read_app_setting(cursor, 'post_default_theme', 'clean_clinical'),
            'wizard_done': read_app_setting(cursor, 'branding_wizard_done', '') == '1',
        }
        conn.close()
        return jsonify(out)
```

(The `wizard_done` field is removed in Task 4.)

- [ ] **Step 4: Delete the two logo routes**

In `dental_clinic.py`, delete this entire block:

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

- [ ] **Step 5: Stop applying a logo when building a spec**

In `dental_clinic.py` `_build_spec_from_request`, replace:

```python
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    logo_path = read_app_setting(cur, 'clinic_logo_path', '')
    doctor = request.form.get('doctor_name') or read_app_setting(cur, 'doctor_name', '') or ''
    conn.close()
    logo = _PILImage.open(logo_path) if logo_path and Path(logo_path).exists() else None
    spec = post_studio.PostSpec(photos=photos, doctor_name=doctor,
                                theme=theme, size=size, logo=logo)
    return spec, None
```

with:

```python
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    doctor = request.form.get('doctor_name') or read_app_setting(cur, 'doctor_name', '') or ''
    conn.close()
    spec = post_studio.PostSpec(photos=photos, doctor_name=doctor,
                                theme=theme, size=size)
    return spec, None
```

(`PostSpec.logo` defaults to `None`, so omitting it is valid and the engine renders no logo.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_post_studio_api.py -v`
Expected: PASS (new tests green; existing preview/save tests still green — they never required a logo).

- [ ] **Step 7: Commit**

```bash
git add dental_clinic.py tests/test_post_studio_api.py
git commit -m "feat(post-studio): remove the clinic logo from branding + post generation"
```

---

### Task 3: Remove the clinic logo from the UI

Delete the logo controls from the Settings → Branding panel, the logo-handling JS, and the logo i18n keys. Update the existing branding UI tests to assert the logo is gone.

**Files:**
- Modify: `templates.py:3024-3031` (branding panel logo `form-group`)
- Modify: `templates.py:6213-6221` (logo preview block in `loadBranding`)
- Modify: `templates.py:6247-6264` (delete `brandingUploadLogo`)
- Modify: `templates.py:3966-3967` (EN logo keys) and `:4439-4440` (AR logo keys)
- Modify: `tests/test_post_studio_ui.py` (trim logo assertions)

**Interfaces:**
- Consumes: nothing new.
- Produces: `HTML_TEMPLATE` with no `branding-logo-preview`, `branding-logo-input`, `brandingUploadLogo`, `ps_branding_logo`, or `ps_branding_logo_upload`.

- [ ] **Step 1: Update the failing tests**

In `tests/test_post_studio_ui.py`:

a) In `test_branding_card_present`, delete these two lines:
```python
    assert 'id="branding-logo-preview"' in HTML_TEMPLATE
    assert 'id="branding-logo-input"' in HTML_TEMPLATE
```

b) In `test_branding_js_functions_present`, delete this line:
```python
    assert 'function brandingUploadLogo(' in HTML_TEMPLATE
```

c) Replace `test_branding_api_calls_correct_endpoints` with (drop the logo half):
```python
def test_branding_api_calls_correct_endpoints():
    """brandingSave uses PUT /api/branding."""
    save_idx = HTML_TEMPLATE.index('function brandingSave()')
    branding_put = HTML_TEMPLATE.find("'/api/branding'", save_idx)
    assert branding_put > save_idx, 'brandingSave does not call /api/branding'
    put_method = HTML_TEMPLATE.find("method: 'PUT'", save_idx)
    assert put_method > save_idx, 'brandingSave does not use PUT method'
```

d) In BOTH `test_branding_translation_keys_in_en` and `test_branding_translation_keys_in_ar`, delete these two list entries:
```python
        'ps_branding_logo',
        'ps_branding_logo_upload',
```

e) Add a new guard test:
```python
def test_branding_logo_ui_removed():
    assert 'branding-logo-preview' not in HTML_TEMPLATE
    assert 'branding-logo-input' not in HTML_TEMPLATE
    assert 'brandingUploadLogo' not in HTML_TEMPLATE
    assert 'ps_branding_logo' not in HTML_TEMPLATE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_post_studio_ui.py::test_branding_logo_ui_removed -v`
Expected: FAIL — logo markup/JS/keys still present.

- [ ] **Step 3: Remove the logo `form-group` from the branding panel**

In `templates.py`, replace:

```html
                    <div class="form-group">
                        <label data-i18n="ps_branding_logo">Clinic logo</label>
                        <img id="branding-logo-preview" src="/api/branding/logo" alt=""
                             style="display:none;max-height:80px;max-width:200px;margin-bottom:8px;border-radius:6px;object-fit:contain;"
                             onerror="this.style.display='none'">
                        <label class="btn" for="branding-logo-input" style="cursor:pointer;margin-bottom:0;" data-i18n="ps_branding_logo_upload">Upload logo</label>
                        <input type="file" id="branding-logo-input" accept="image/*" style="display:none" onchange="brandingUploadLogo(this)">
                    </div>
                    <button class="btn btn-primary" type="button" onclick="brandingSave()" data-i18n="ps_branding_save">Save branding</button>
```

with:

```html
                    <button class="btn btn-primary" type="button" onclick="brandingSave()" data-i18n="ps_branding_save">Save branding</button>
```

- [ ] **Step 4: Remove the logo preview block in `loadBranding`**

In `templates.py`, replace:

```javascript
                if (themeEl && data.default_theme) themeEl.value = data.default_theme;
                const preview = document.getElementById('branding-logo-preview');
                if (preview) {
                    if (data.has_logo) {
                        preview.src = '/api/branding/logo?_t=' + Date.now();
                        preview.style.display = '';
                    } else {
                        preview.style.display = 'none';
                    }
                }
            } catch (_) {}
```

with:

```javascript
                if (themeEl && data.default_theme) themeEl.value = data.default_theme;
            } catch (_) {}
```

- [ ] **Step 5: Delete the `brandingUploadLogo` function**

In `templates.py`, delete this entire function (the blank line before `loadReceivables` stays):

```javascript
        async function brandingUploadLogo(input) {
            const file = input.files && input.files[0];
            if (!file) return;
            const fd = new FormData();
            fd.append('logo', file);
            try {
                const res = await fetch('/api/branding/logo', { method: 'POST', body: fd });
                if (!res.ok) throw new Error(res.status);
                const preview = document.getElementById('branding-logo-preview');
                if (preview) {
                    preview.src = '/api/branding/logo?_t=' + Date.now();
                    preview.style.display = '';
                }
                showToast(t('ps_branding_saved', 'Branding saved'), 'success');
            } catch (err) {
                showToast(t('ps_branding_save_failed', 'Could not save branding: ') + err, 'error');
            }
        }

```

- [ ] **Step 6: Remove the logo i18n keys (EN + AR)**

In `templates.py`, delete the EN pair:

```javascript
                ps_branding_logo: 'Clinic logo',
                ps_branding_logo_upload: 'Upload logo',
```

and the AR pair:

```javascript
                ps_branding_logo: 'شعار العيادة',
                ps_branding_logo_upload: 'رفع الشعار',
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_post_studio_ui.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add templates.py tests/test_post_studio_ui.py
git commit -m "feat(post-studio): drop the clinic-logo controls from the branding UI"
```

---

### Task 4: Remove the first-run branding wizard

Delete the wizard modal, its JS controller (including the auto-show on first login), the `wizard-done` endpoint, the `wizard_done` field, and the wizard i18n keys. Branding now lives only in the Settings panel and never pops up.

**Files:**
- Modify: `templates.py:3402-3461` (wizard modal markup)
- Modify: `templates.py:9328-9457` (wizard JS IIFE + auto-show)
- Modify: `templates.py:3971-3985` (EN wizard keys) and `:4444-4458` (AR wizard keys)
- Modify: `dental_clinic.py:4720` (drop `wizard_done` from branding GET)
- Modify: `dental_clinic.py:4775-4782` (delete `/api/branding/wizard-done` route)
- Modify: `tests/test_post_studio_ui.py` and `tests/test_post_studio_api.py`

**Interfaces:**
- Consumes: `client`/`_login` fixtures.
- Produces: no wizard markup/JS/keys; no `/api/branding/wizard-done` route; `GET /api/branding` JSON without `wizard_done`.

- [ ] **Step 1: Write/Update the failing tests**

a) In `tests/test_post_studio_ui.py`, delete the entire "Task 13: First-run branding wizard" section — every `test_wizard_*` function (from the `# ── Task 13` comment through the last `test_wizard_translation_keys_in_ar`). Then add:

```python
def test_branding_wizard_removed():
    assert 'branding-wizard-modal' not in HTML_TEMPLATE
    assert 'wizard-done' not in HTML_TEMPLATE
    assert 'ps_wizard_title' not in HTML_TEMPLATE
    assert 'bwShow' not in HTML_TEMPLATE
```

b) In `tests/test_post_studio_api.py`, add:

```python
def test_wizard_done_endpoint_is_gone(client):
    _login(client)
    assert client.post('/api/branding/wizard-done').status_code == 404


def test_branding_get_has_no_wizard_field(client):
    _login(client)
    body = client.get('/api/branding').get_json()
    assert 'wizard_done' not in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_post_studio_ui.py::test_branding_wizard_removed tests/test_post_studio_api.py::test_wizard_done_endpoint_is_gone tests/test_post_studio_api.py::test_branding_get_has_no_wizard_field -v`
Expected: FAIL — wizard markup/route/field still present.

- [ ] **Step 3: Delete the wizard modal markup**

In `templates.py`, delete the whole block starting at the `<!-- Branding Wizard Modal -->` comment (line ~3402) through the modal's closing `</div>` that ends it (line ~3461). The block opens with:

```html
    <!-- Branding Wizard Modal -->
    <div id="branding-wizard-modal" class="modal" role="dialog" aria-modal="true" aria-labelledby="bw-title">
```

and ends at the matching `</div>` of `#branding-wizard-modal` (immediately before the next top-level template section). Remove the entire modal, leaving no `bw-*` elements behind.

- [ ] **Step 4: Delete the wizard JS controller**

In `templates.py`, delete the entire wizard IIFE and its comment header — from:

```javascript
        // ── Branding wizard ──────────────────────────────────────────────────
```

through the IIFE's closing line:

```javascript
        })();
```

(this is the `(function () { … })();` that defines `bwShow`, `bwGoStep`, `bwDone`, `bwWireButtons`, and the `DOMContentLoaded` auto-show that calls `bwShow()`).

- [ ] **Step 5: Remove the wizard i18n keys (EN + AR)**

In `templates.py`, delete the EN wizard block:

```javascript
                ps_wizard_title: 'Set Up Your Clinic Branding',
                ps_wizard_subtitle: 'Personalise posts with your name, logo, and preferred style',
                ps_wizard_step1: 'Doctor Name',
                ps_wizard_step2: 'Clinic Logo',
                ps_wizard_step3: 'Default Theme',
                ps_wizard_name_en: 'Your name (English)',
                ps_wizard_name_ar: 'Your name (Arabic)',
                ps_wizard_logo_hint: 'Upload your clinic logo — shown on every post',
                ps_wizard_theme_hint: 'Choose the default visual style for new posts',
                ps_wizard_skip: 'Skip Setup',
                ps_wizard_back: 'Back',
                ps_wizard_next: 'Next',
                ps_wizard_finish: 'Finish',
                ps_wizard_saving: 'Saving…',
                ps_wizard_done_toast: 'Branding set up successfully'
```

and the AR wizard block:

```javascript
                ps_wizard_title: 'إعداد هوية عيادتك',
                ps_wizard_subtitle: 'خصّص منشوراتك باسمك وشعارك وأسلوبك المفضّل',
                ps_wizard_step1: 'اسم الطبيب',
                ps_wizard_step2: 'شعار العيادة',
                ps_wizard_step3: 'الثيم الافتراضي',
                ps_wizard_name_en: 'اسمك (بالإنجليزية)',
                ps_wizard_name_ar: 'اسمك (بالعربية)',
                ps_wizard_logo_hint: 'ارفع شعار عيادتك — يظهر على كل منشور',
                ps_wizard_theme_hint: 'اختر الأسلوب البصري الافتراضي للمنشورات الجديدة',
                ps_wizard_skip: 'تخطّي الإعداد',
                ps_wizard_back: 'رجوع',
                ps_wizard_next: 'التالي',
                ps_wizard_finish: 'إنهاء',
                ps_wizard_saving: 'جارٍ الحفظ…',
                ps_wizard_done_toast: 'تم إعداد العلامة التجارية بنجاح'
```

Both blocks are preceded by a line ending in a comma (the `ps_branding_save_failed` key), which stays. Make sure the key immediately before each deleted block still ends correctly (the object closes cleanly).

- [ ] **Step 6: Drop `wizard_done` from the branding GET**

In `dental_clinic.py`, replace:

```python
            'default_theme': read_app_setting(cursor, 'post_default_theme', 'clean_clinical'),
            'wizard_done': read_app_setting(cursor, 'branding_wizard_done', '') == '1',
        }
```

with:

```python
            'default_theme': read_app_setting(cursor, 'post_default_theme', 'clean_clinical'),
        }
```

- [ ] **Step 7: Delete the `wizard-done` route**

In `dental_clinic.py`, delete:

```python
@app.route('/api/branding/wizard-done', methods=['POST'])
def branding_wizard_done():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    write_app_setting(cur, 'branding_wizard_done', '1')
    conn.commit()
    conn.close()
    return jsonify({'success': True})


```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_post_studio_ui.py tests/test_post_studio_api.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add templates.py dental_clinic.py tests/test_post_studio_ui.py tests/test_post_studio_api.py
git commit -m "feat(post-studio): remove the first-run branding wizard (no popup)"
```

---

### Task 5: Full-suite verification + boot smoke (phase gate)

Confirm nothing else regressed and the inline JS still parses after deleting the wizard script.

**Files:** none (verification only).

- [ ] **Step 1: Run the entire test suite**

Run: `python -m pytest tests/`
Then check the exit code (the repo suppresses the summary): `echo $LASTEXITCODE` (PowerShell: `$LASTEXITCODE`).
Expected: exit code `0`.

- [ ] **Step 2: Confirm the template still imports and the wizard JS is gone**

Run: `python -c "import templates; assert 'bwShow' not in templates.HTML_TEMPLATE and '#i-image' in templates.HTML_TEMPLATE; print('ok')"`
Expected: prints `ok` (no SyntaxError — the inline `<script>` is still balanced).

- [ ] **Step 3: Boot smoke (manual checkpoint)**

Launch the desktop app (or `python dental_clinic.py`), log in, open **Post Studio** (icon is now an image glyph), open **Settings → Branding** (name EN/AR + default theme only — no logo control), and confirm **no wizard pops up** on a fresh login.
Expected: all three hold; existing generate/preview/save still works.

- [ ] **Step 4: (No commit needed.)** P1 is PR-ready. Open the PR or proceed to plan P2.

---

## Self-Review

- **Spec coverage (P1 scope):** icon swap → Task 1; remove clinic logo (backend + UI) → Tasks 2–3; remove first-run wizard → Task 4; tests/green gate → all tasks + Task 5. ✓
- **Placeholder scan:** every code step shows exact old/new text or exact deletion blocks; the icon uses a real Phosphor Image path; no TBDs. ✓
- **Type/name consistency:** `i-image` symbol id ↔ `#i-image` reference; `has_logo`/`wizard_done` removed from the same GET dict across Tasks 2 & 4 (sequential edits target distinct lines); `brandingUploadLogo`, `ps_branding_logo*`, `ps_wizard_*`, `branding-wizard-modal`, `/api/branding/logo`, `/api/branding/wizard-done` all removed and guarded by absence tests. ✓
- **Deliberately deferred:** themes unchanged (P3); `post_studio.PostSpec.logo` + engine logo block left in place (deleted wholesale in P2). ✓
