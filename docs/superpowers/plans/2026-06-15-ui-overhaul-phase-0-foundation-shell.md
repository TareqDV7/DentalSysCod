# UI/UX Overhaul Phase 0 — Foundation + Shared Chrome Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the desktop portal's foundation (self-hosted fonts + icons, consolidated design tokens, logo-blue accent) and reskin the shared chrome (header + left sidebar) into the "Editorial Slate" direction, in both light and dark themes, without changing layout, markup structure, behavior, mobile, or data.

**Architecture:** All edits are confined to `templates.py` (the `HTML_TEMPLATE` string) plus two new Python modules. Fonts and icons are vendored as a generated Python module (`web_assets.py`) holding base64 `@font-face` CSS and an inline SVG `<symbol>` sprite — so they ship inside the code (no `static/` serving, no PyInstaller `datas` edits) and render fully offline. Tokens are consolidated into one `:root` block; the accent flips from teal `#13b5a7` to blue `#38bdf8` with a fills-only teal→blue `--accent-gradient`. The shared chrome (`.header`, `.nav-tabs`, `.nav-tab`, `.nav-subtab`) is recolored; structure is untouched.

**Tech Stack:** Python 3 / Flask (`render_template_string`), pytest, Phosphor Icons (`@phosphor-icons/core`, MIT) as the icon source, Space Grotesk + Manrope (Google Fonts, OFL) as the font source, Playwright for visual smoke.

**Spec:** `docs/superpowers/specs/2026-06-15-ui-overhaul-phase-0-foundation-shell-design.md`
**Branch:** `feat/ui-overhaul-p0` (already created; spec already committed)

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `tools/gen_web_assets.py` | One-time generator: download pinned woff2 subsets + Phosphor SVGs, emit `web_assets.py`. Network needed only when (re)generating. | Create |
| `web_assets.py` | Generated, committed: `FONT_FACE_CSS` (base64 data-URI `@font-face`), `ICON_SPRITE` (inline `<symbol>` defs), `ICON_NAMES`, `render_icon()` helper. | Create |
| `templates.py` | Inject font CSS + icon sprite into `HTML_TEMPLATE`; remove the Google Fonts `@import`; consolidate/harden the `:root` tokens; flip accent; reskin header + sidebar + nav; dark-theme shell tokens. | Modify |
| `tests/test_ui_overhaul_p0.py` | Assert the foundation invariants against `HTML_TEMPLATE` and `web_assets` (no CDN, fonts inlined, sprite complete, accent flipped, tokens present, shell recolored). | Create |
| `docs/superpowers/specs/.../...md` | The design spec. | Already committed |

No changes to: mobile (`clinic_mobile_app/`), `dental_clinic.py` logic, the DB, any API, or `DentaCare.spec` (assets live in a `.py` module, auto-bundled).

---

## Task 1: Vendored web assets (fonts + icon sprite)

Generate a committed `web_assets.py` holding self-hosted fonts (base64) and the icon sprite, so nothing loads from a CDN at runtime.

**Files:**
- Create: `tools/gen_web_assets.py`
- Create: `web_assets.py` (produced by the generator, then committed)
- Test: `tests/test_ui_overhaul_p0.py`

- [ ] **Step 1: Write the generator script**

Create `tools/gen_web_assets.py`. It (a) fetches the Google Fonts CSS for the exact families/weights with a woff2-capable UA, downloads the **latin** `@font-face` woff2 files, base64-inlines them; (b) downloads the 13 Phosphor SVGs (`regular` + `house` from `fill`) from the pinned `@phosphor-icons/core` package and assembles an inline `<symbol>` sprite. Output is written to `web_assets.py`.

```python
"""Generate web_assets.py: base64 @font-face CSS + inline Phosphor icon sprite.

Run once (needs network) whenever fonts/icons change:
    python tools/gen_web_assets.py
The OUTPUT (web_assets.py) is committed; runtime never hits the network.
"""
from __future__ import annotations
import base64, re, sys, urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web_assets.py"

# (family, weights) — must match the weights used in the shell.
FONTS = [("Manrope", [400, 500, 600, 700, 800]), ("Space+Grotesk", [500, 600, 700])]
GF_CSS = "https://fonts.googleapis.com/css2?family={fam}:wght@{wts}&display=swap"
# A modern Chrome UA makes Google serve woff2 (the WebView2/Chromium runtime).
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

PHOSPHOR_VER = "2.1.1"
CORE = f"https://unpkg.com/@phosphor-icons/core@{PHOSPHOR_VER}/assets"
ICONS = ["house", "users", "calendar-dots", "receipt", "gear", "magnifying-glass",
         "bell", "caret-down", "moon", "sun", "sign-out", "user", "user-plus"]
FILL_ICONS = ["house"]  # active-item only

def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def build_font_css() -> str:
    blocks = []
    for fam, weights in FONTS:
        css = _get(GF_CSS.format(fam=fam, wts=";".join(map(str, weights)))).decode()
        # Keep only latin @font-face blocks; inline their woff2 as data URIs.
        for m in re.finditer(r"/\*\s*latin\s*\*/\s*(@font-face\s*{[^}]+})", css):
            block = m.group(1)
            url_m = re.search(r"url\((https://[^)]+\.woff2)\)", block)
            if not url_m:
                continue
            b64 = base64.b64encode(_get(url_m.group(1))).decode()
            data_uri = f"url(data:font/woff2;base64,{b64}) format('woff2')"
            blocks.append(re.sub(r"url\([^)]+\)\s*format\('woff2'\)", data_uri, block))
    return "\n".join(blocks)

def build_sprite() -> str:
    symbols = []
    def fetch_inner(weight: str, name: str) -> str:
        suffix = "" if weight == "regular" else f"-{weight}"
        svg = _get(f"{CORE}/{weight}/{name}{suffix}.svg").decode()
        inner = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1).strip()
        if "<path" not in inner:
            raise SystemExit(f"FAIL: {weight}/{name} produced no <path>")
        return inner
    for name in ICONS:
        symbols.append(f'<symbol id="i-{name}" viewBox="0 0 256 256">{fetch_inner("regular", name)}</symbol>')
    for name in FILL_ICONS:
        symbols.append(f'<symbol id="i-{name}-fill" viewBox="0 0 256 256">{fetch_inner("fill", name)}</symbol>')
    return ('<svg width="0" height="0" style="position:absolute" aria-hidden="true">'
            + "".join(symbols) + "</svg>")

def main() -> None:
    font_css = build_font_css()
    sprite = build_sprite()
    names = ICONS
    body = (
        '"""GENERATED by tools/gen_web_assets.py — do not edit by hand."""\n\n'
        f"ICON_NAMES = {tuple(names)!r}\n\n"
        f'FONT_FACE_CSS = """{font_css}"""\n\n'
        f"ICON_SPRITE = {sprite!r}\n\n"
        "def render_icon(name, fill=False):\n"
        '    """Return <svg><use/></svg> markup referencing the inline sprite."""\n'
        "    ref = f'#i-{name}-fill' if fill else f'#i-{name}'\n"
        "    cls = 'ic ic-fill' if fill else 'ic'\n"
        '    return f\'<svg class="{cls}" aria-hidden="true"><use href="{ref}"/></svg>\'\n'
    )
    OUT.write_text(body, encoding="utf-8")
    print(f"wrote {OUT} ({len(font_css)} B css, {len(names)} icons)")

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the generator**

Run: `python tools/gen_web_assets.py`
Expected: prints `wrote .../web_assets.py (NNNNN B css, 13 icons)` and creates `web_assets.py`. (Requires network this once.)

- [ ] **Step 3: Write the failing test for the vendored assets**

Create `tests/test_ui_overhaul_p0.py`:

```python
import web_assets


def test_font_css_is_inlined_woff2_for_required_families():
    css = web_assets.FONT_FACE_CSS
    assert css.count("@font-face") >= 8, "expected >=8 @font-face blocks (5 Manrope + 3 Space Grotesk)"
    assert "data:font/woff2;base64," in css, "fonts must be base64-inlined, not linked"
    assert "fonts.googleapis.com" not in css and "http" not in css, "no remote URLs in font CSS"
    assert "Manrope" in css and "Space Grotesk" in css


def test_icon_sprite_has_all_symbols_with_paths():
    assert set(web_assets.ICON_NAMES) >= {
        "house", "users", "calendar-dots", "receipt", "gear", "magnifying-glass",
        "bell", "caret-down", "moon", "sun", "sign-out", "user", "user-plus",
    }
    sprite = web_assets.ICON_SPRITE
    for name in web_assets.ICON_NAMES:
        assert f'id="i-{name}"' in sprite, f"missing symbol {name}"
    assert 'id="i-house-fill"' in sprite, "active-item needs a fill house"
    # Every symbol must carry real geometry (guards against the truncated-path bug).
    assert sprite.count("<path") >= len(web_assets.ICON_NAMES)


def test_render_icon_emits_use_reference():
    assert web_assets.render_icon("bell") == '<svg class="ic" aria-hidden="true"><use href="#i-bell"/></svg>'
    assert web_assets.render_icon("house", fill=True) == '<svg class="ic ic-fill" aria-hidden="true"><use href="#i-house-fill"/></svg>'
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_ui_overhaul_p0.py -v`
Expected: 3 passed. (If `test_icon_sprite...` fails on a missing path, the generator caught a bad icon name — fix the name list, regenerate.)

- [ ] **Step 5: Commit**

```bash
git add tools/gen_web_assets.py web_assets.py tests/test_ui_overhaul_p0.py
git commit -m "feat(ui-p0): vendor self-hosted fonts + Phosphor icon sprite"
```

---

## Task 2: Self-host fonts in the template (remove the Google CDN)

Inject the base64 `@font-face` CSS into `HTML_TEMPLATE` and delete the `fonts.googleapis.com` `@import`.

**Files:**
- Modify: `templates.py:8` (top of `HTML_TEMPLATE`) and `templates.py:16` (the `@import`)
- Test: `tests/test_ui_overhaul_p0.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ui_overhaul_p0.py`:

```python
from templates import HTML_TEMPLATE


def test_template_has_no_google_fonts_cdn():
    assert "fonts.googleapis.com" not in HTML_TEMPLATE
    assert "fonts.gstatic.com" not in HTML_TEMPLATE


def test_template_inlines_self_hosted_fonts():
    assert "@font-face" in HTML_TEMPLATE
    assert "data:font/woff2;base64," in HTML_TEMPLATE
    # families still referenced by the UI
    assert "Space Grotesk" in HTML_TEMPLATE and "Manrope" in HTML_TEMPLATE
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_ui_overhaul_p0.py::test_template_has_no_google_fonts_cdn -v`
Expected: FAIL — `fonts.googleapis.com` is still present (line 16).

- [ ] **Step 3: Inject the font CSS and remove the CDN import**

In `templates.py`, at the very top of the module (after the docstring, before `HTML_TEMPLATE = '''`), add the import:

```python
from web_assets import FONT_FACE_CSS, ICON_SPRITE, render_icon  # noqa: F401  (ICON_SPRITE/render_icon used by later tasks)
```

Replace the Google Fonts `@import` line (currently `templates.py:16`):

```css
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Space+Grotesk:wght@600;700&display=swap');
```

with a sentinel comment that we substitute after the literal:

```css
        /*__FONT_FACE__*/
```

Then, immediately **after** the `HTML_TEMPLATE = '''...'''` literal ends, add (the replace runs at import, before Jinja ever sees the string — no `{{ }}` involved, so the JS-escaping trap does not apply):

```python
HTML_TEMPLATE = HTML_TEMPLATE.replace("/*__FONT_FACE__*/", FONT_FACE_CSS)
```

- [ ] **Step 4: Run the font tests to verify they pass**

Run: `python -m pytest tests/test_ui_overhaul_p0.py -k "font or cdn" -v`
Expected: PASS (`test_template_has_no_google_fonts_cdn`, `test_template_inlines_self_hosted_fonts`).

- [ ] **Step 5: Commit**

```bash
git add templates.py tests/test_ui_overhaul_p0.py
git commit -m "feat(ui-p0): self-host fonts inline, drop Google Fonts CDN"
```

---

## Task 3: Install the icon sprite (inline, offline)

Place the `<symbol>` sprite once at the top of `<body>` so `<use href="#i-...">` works anywhere in the page.

**Files:**
- Modify: `templates.py` (inside `HTML_TEMPLATE`, just after the opening `<body...>` tag)
- Test: `tests/test_ui_overhaul_p0.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ui_overhaul_p0.py`:

```python
def test_template_embeds_icon_sprite():
    assert 'id="i-house"' in HTML_TEMPLATE and 'id="i-house-fill"' in HTML_TEMPLATE
    assert 'id="i-gear"' in HTML_TEMPLATE  # the icon the mockup broke — must be real
    assert "unpkg.com" not in HTML_TEMPLATE  # never the CDN webfont at runtime
    assert "@phosphor-icons/web" not in HTML_TEMPLATE
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_ui_overhaul_p0.py::test_template_embeds_icon_sprite -v`
Expected: FAIL — sprite not present yet.

- [ ] **Step 3: Inject the sprite**

Find the `<body ...>` opening tag inside `HTML_TEMPLATE` (it carries the `data-theme` attribute). Immediately after it, add a sentinel:

```html
    <!--__ICON_SPRITE__-->
```

After the literal (next to the font replace line from Task 2), add:

```python
HTML_TEMPLATE = HTML_TEMPLATE.replace("<!--__ICON_SPRITE__-->", ICON_SPRITE)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_ui_overhaul_p0.py::test_template_embeds_icon_sprite -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates.py tests/test_ui_overhaul_p0.py
git commit -m "feat(ui-p0): embed inline Phosphor icon sprite"
```

---

## Task 4: Consolidate + harden design tokens (accent teal → blue)

Merge the two `:root` blocks into one, add radius/elevation/motion scales and the gradient token, flip the accent, and complete the dark-theme token set.

**Files:**
- Modify: `templates.py:18-32` (first `:root`), `templates.py:47-59` (dark override), `templates.py:756-765` (spacing `:root`)
- Test: `tests/test_ui_overhaul_p0.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ui_overhaul_p0.py`:

```python
def test_accent_flipped_to_blue():
    assert "--accent: #38bdf8;" in HTML_TEMPLATE
    assert "#13b5a7" not in HTML_TEMPLATE, "teal accent must be fully removed"


def test_gradient_and_new_scales_present():
    for token in ("--accent-teal:", "--accent-gradient:", "--radius-lg:", "--elev-card:", "--dur:"):
        assert token in HTML_TEMPLATE, f"missing token {token}"


def test_dark_theme_canvas_and_surface_tokens():
    # dark block must redefine the data canvas + surface as opaque slate
    assert "--canvas: #020617;" in HTML_TEMPLATE
    assert "--surface: #1e293b;" in HTML_TEMPLATE
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_ui_overhaul_p0.py -k "accent or gradient or dark_theme" -v`
Expected: FAIL — new tokens absent, teal still present.

- [ ] **Step 3: Replace the first `:root` block (`templates.py:18-32`) with the consolidated block**

```css
        :root {
            /* chrome (header + sidebar) — slate in BOTH themes */
            --chrome-bg: #0f172a;
            --chrome-bg-2: #0b1220;
            --chrome-border: rgba(255,255,255,.06);
            /* content */
            --canvas: #f1f5f9;
            --surface: #ffffff;              /* solid data card — never frosted */
            --surface-border: rgba(15,23,42,.07);
            /* ink (text/icons/rails/rings) */
            --ink: #0f172a;
            --ink-muted: #64748b;
            --ink-subtle: #94a3b8;
            /* accent — solid blue ink, teal->blue gradient on FILLS only */
            --accent: #38bdf8;               /* was #13b5a7 teal */
            --accent-strong: #1d7fb7;
            --accent-cta-from: #1d7fb7;
            --accent-cta-to: #2563eb;
            --accent-soft: rgba(56,189,248,.13);
            --accent-teal: #14b8a6;          /* gradient stop — fills only, never ink */
            --accent-gradient: linear-gradient(135deg, var(--accent-teal), var(--accent-cta-to));
            /* legacy names kept so existing rules don't break */
            --bg-1: #f1f7f8;
            --bg-2: #e7f0ff;
            --panel: #ffffff;
            --line: #dbe4ef;
            --text: #11243a;
            --muted: #627386;
            --brand: #0f6d7b;
            --brand-2: #1d7fb7;
            --danger: #d9434e;
            --warning: #d89e1f;
            --ok: #1f9a5f;
            /* spacing (moved here from the second :root) */
            --space-1: 6px; --space-2: 10px; --space-3: 14px;
            --space-4: 18px; --space-5: 24px; --space-6: 32px;
            --gap: var(--space-3);
            --input-padding: 12px 14px;
            /* radius */
            --radius-sm: 8px; --radius-md: 11px; --radius-lg: 14px;
            --radius-xl: 16px; --radius-pill: 999px;
            /* elevation (opaque) */
            --shadow: 0 14px 36px rgba(19, 39, 66, 0.12);
            --elev-card: 0 10px 30px -16px rgba(15,23,42,.30);
            --elev-raised: 0 24px 60px -24px rgba(15,23,42,.50);
            /* motion */
            --dur-fast: 150ms; --dur: 300ms; --ease: cubic-bezier(.16,1,.3,1);
        }
```

- [ ] **Step 4: Delete the now-duplicate spacing `:root` (`templates.py:756-765`)**

Remove the entire second `:root { --space-1 ... --input-padding ...}` block (its tokens now live in the consolidated block). Leave the surrounding rules (e.g. `.form-group textarea`) intact.

- [ ] **Step 5: Extend the dark override (`templates.py:47-59`) with the data-surface tokens**

Inside the existing `body[data-theme="dark"] {` block, add these lines (keep the existing `--bg-1/--bg-2/--panel/...` lines):

```css
            --canvas: #020617;               /* slate-950 content canvas */
            --surface: #1e293b;              /* solid slate-800 data card (opaque) */
            --surface-border: rgba(255,255,255,.07);
            --ink: #f1f5f9;
            --warning: #fbbf24;              /* lightened so 'due' stays legible on dark */
            --elev-card: 0 12px 34px -16px rgba(0,0,0,.6);
            /* chrome tokens unchanged — chrome is slate in both themes */
```

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/test_ui_overhaul_p0.py -k "accent or gradient or dark_theme" -v`
Expected: PASS (3 tests). Also re-run the full new file: `python -m pytest tests/test_ui_overhaul_p0.py -v` → all green.

- [ ] **Step 7: Commit**

```bash
git add templates.py tests/test_ui_overhaul_p0.py
git commit -m "feat(ui-p0): consolidate tokens, flip accent to blue, add gradient/scales + dark surfaces"
```

---

## Task 5: Reskin the shared chrome (Editorial Slate)

Recolor header + sidebar + nav to slate, wire the sprite icons + Fill-active item + gradient fills. **No structural/markup-layout change** — restyle existing classes and swap control glyphs.

**Files:**
- Modify: `templates.py` — CSS for `.header`, `.nav-tabs`, `.nav-tab`, `.nav-tab.active`/active marker, `.nav-subtab`, and the data card/surface classes; header control markup (swap emoji → `<use>` icons).
- Test: `tests/test_ui_overhaul_p0.py` (sentinel asserts; visual smoke is the real check in Task 6)

- [ ] **Step 1: Write the failing sentinel test**

Append to `tests/test_ui_overhaul_p0.py`:

```python
def test_chrome_uses_slate_tokens_not_old_light_sidebar():
    # the sidebar was a light #f3f7fb panel; after reskin it must use the chrome token
    assert "--chrome-bg" in HTML_TEMPLATE
    # active nav item references the fill icon + gradient/accent treatment
    assert "i-house-fill" in HTML_TEMPLATE
    assert "use href=\"#i-" in HTML_TEMPLATE  # controls are sprite icons, not emoji


def test_data_card_uses_surface_token():
    assert "var(--surface)" in HTML_TEMPLATE
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_ui_overhaul_p0.py -k "chrome or surface" -v`
Expected: FAIL — sprite controls / chrome tokens not wired yet.

- [ ] **Step 3: Restyle the header (`.header`)**

Locate the `.header { ... }` rule and its dark override. Set its background to the chrome token and keep the existing layout/flex. Replace its background/border declarations:

```css
        .header {
            /* keep existing display/flex/padding/gap lines as-is; only color changes */
            background: rgba(15, 23, 42, .94);
            backdrop-filter: blur(12px);                 /* glass is allowed on CHROME */
            border-bottom: 1px solid var(--chrome-border);
            color: #e2e8f0;
        }
```

(Existing `body[data-theme="dark"] .header { ... }` can be removed or set equal — the header is slate in both themes.)

- [ ] **Step 4: Restyle the sidebar (`.nav-tabs`, `.nav-tabs-label`, `.nav-group-label`)**

Replace the light backgrounds with chrome tokens; keep `width: 196px` and the flex column:

```css
        .nav-tabs {
            /* keep flex-direction/column, width:196px, padding, overflow as-is */
            background: var(--chrome-bg);
            border-right: 1px solid var(--chrome-border);
        }
        .nav-tabs-label, .nav-group-label {
            color: var(--ink-subtle);
        }
```

Remove (or neutralize) the old `body[data-theme="dark"] .nav-tabs { background:#10192a; ... }` override since the sidebar is slate in both themes.

- [ ] **Step 5: Restyle nav items + the active item (`.nav-tab`, `.nav-subtab`)**

```css
        .nav-tab, .nav-subtab {
            color: var(--ink-subtle);
            border-radius: var(--radius-md);
            transition: background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease);
        }
        .nav-tab:hover, .nav-subtab:hover { color: #cbd5e1; background: rgba(255,255,255,.05); }
        .nav-tab.active, .nav-subtab.active {
            color: #7dd3fc;                              /* solid blue ink */
            font-weight: 700;
            background: var(--accent-gradient);          /* teal->blue fill ... */
            background: linear-gradient(135deg, rgba(20,184,166,.16), rgba(56,189,248,.16)); /* ...as a soft tint */
            box-shadow: inset 3px 0 0 var(--accent);
        }
```

- [ ] **Step 6: Swap the header control glyphs to sprite icons**

In the `.header` markup, locate the existing control elements (theme toggle, language EN/AR, logout, patient search, notifications, doctor badge caret). Replace each emoji/text glyph with the matching `<use>` markup. Exact snippets:

```html
<!-- search -->        <svg class="ic"><use href="#i-magnifying-glass"/></svg>
<!-- notifications -->  <svg class="ic"><use href="#i-bell"/></svg>
<!-- doctor caret -->   <svg class="ic"><use href="#i-caret-down"/></svg>
<!-- theme (light) -->  <svg class="ic"><use href="#i-moon"/></svg>
<!-- theme (dark)  -->  <svg class="ic"><use href="#i-sun"/></svg>
<!-- logout -->         <svg class="ic"><use href="#i-sign-out"/></svg>
```

For the sidebar nav items, prepend each label with its icon; the active (Dashboard) item uses the fill variant:

```html
<!-- active Dashboard --> <svg class="ic ic-fill"><use href="#i-house-fill"/></svg>
<!-- Patients -->         <svg class="ic"><use href="#i-users"/></svg>
<!-- Appointments -->     <svg class="ic"><use href="#i-calendar-dots"/></svg>
<!-- Billing -->          <svg class="ic"><use href="#i-receipt"/></svg>
<!-- Settings -->         <svg class="ic"><use href="#i-gear"/></svg>
```

Add the icon sizing CSS once (near the other shell rules):

```css
        .ic { width: 1.18em; height: 1.18em; display: inline-block; vertical-align: -0.18em; fill: currentColor; }
        .nav-tab .ic, .nav-subtab .ic { width: 19px; height: 19px; }
```

- [ ] **Step 7: Point the data card + content canvas at the surface tokens**

Find the primary content-card/panel class (e.g. `.stat-card` container and the main content wrapper) and ensure cards use the solid surface tokens:

```css
        /* apply to the data card/panel class used for record lists & detail cards */
        .card, .panel-surface {
            background: var(--surface);
            border: 1px solid var(--surface-border);
            border-radius: var(--radius-lg);
            box-shadow: var(--elev-card);
        }
```

(If the existing card class differs, apply these four declarations to it. Do **not** add `backdrop-filter` to data surfaces — solid only.)

- [ ] **Step 8: Run sentinel tests + full file**

Run: `python -m pytest tests/test_ui_overhaul_p0.py -v`
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add templates.py tests/test_ui_overhaul_p0.py
git commit -m "feat(ui-p0): reskin shared chrome to Editorial Slate (header, sidebar, nav, cards)"
```

---

## Task 6: Verification — full suite, render, offline, visual smoke

No new code; prove the reskin is correct and regression-free.

**Files:** none (verification only)

- [ ] **Step 1: Full test suite stays green**

Run: `python -m pytest tests/` then check `echo $LASTEXITCODE` (the summary is suppressed in this harness — exit 0 means green).
Expected: exit 0. Phase 0 changes no behavior, so prior tests must be unaffected.

- [ ] **Step 2: Template renders without error**

Run:
```bash
python -c "from flask import Flask, render_template_string; from templates import HTML_TEMPLATE; import dental_clinic as d; app=Flask(__name__); ctx=getattr(d,'CLINIC_CONFIG',{}); app.app_context().push(); render_template_string(HTML_TEMPLATE, **ctx); print('RENDER OK')"
```
Expected: `RENDER OK` (no Jinja/escaping error). If `CLINIC_CONFIG` needs more keys, pass the same kwargs used at `dental_clinic.py:2158`.

- [ ] **Step 2b: Escaping sweep (the templates.py JS trap)**

Confirm no inline `<script>` broke from the edits: grep the rendered HTML for an obvious syntax canary and load it in a headless check during Step 3. (Phase 0 edits CSS/markup only, but the file's history warrants the sweep.)

- [ ] **Step 3: Playwright visual smoke — light + dark**

Per the web-visual-smoke recipe (fresh temp DB → unlicensed gate; seed an active license, log in `admin`/`admin`): screenshot the portal shell at desktop width in light and dark (`data-theme`), and confirm:
- header + sidebar are dark slate in both themes;
- active nav item is the Fill house with the soft gradient tint + accent text;
- data cards are solid (not frosted), legible;
- the "due" amount is legible in dark;
- **no teal `#13b5a7` remains** on inner surfaces (active tabs, focus rings) — the accent-flip follow-up from the spec;
- **no console errors**.

- [ ] **Step 4: Offline proof**

Load the portal with the network disabled. Fonts and icons must still render (proves self-hosting; nothing fetches from googleapis/unpkg).

- [ ] **Step 5: Commit any smoke fixes, then summary commit if needed**

```bash
git add -A && git commit -m "test(ui-p0): visual smoke + render verification notes" || echo "nothing to commit"
```

---

## Task 7 (deferred to user): Packaged-exe check

After merge, rebuild `installer\Output\DentaCare-Setup.exe` and confirm the self-hosted fonts + icons render in the WebView2 shell (no CDN, offline). This is a user-side build step, not part of the automated plan.

---

## Self-Review

**1. Spec coverage:**
- Self-host fonts → Tasks 1–2. ✓
- Self-host Phosphor subset (Regular + Fill-active) → Tasks 1, 3, 5 (fill house on active). ✓
- Consolidate/harden tokens + radius/elevation/motion → Task 4. ✓
- Accent flip teal→blue + `--accent-gradient` fills-only → Task 4 (tokens), Task 5 (applied to active pill/fills). ✓
- Reskin shared chrome (header + sidebar), both themes → Task 5 + Task 4 dark set. ✓
- Glass-for-chrome/solid-for-data rule → Task 5 (blur on `.header` only; cards solid). ✓
- Verification (render, offline, visual both themes, suite green, exe) → Tasks 6–7. ✓
- Non-goals (no mobile/JS/DB/API) → honored; only `templates.py` + 2 new asset modules touched. ✓

**2. Placeholder scan:** No TBD/TODO; every code step carries complete code or an exact edit with the literal CSS/markup. Asset path-data is vendored by the generator (not hand-transcribed) — the deliberate fix for the truncated-gear bug.

**3. Type/name consistency:** `FONT_FACE_CSS`, `ICON_SPRITE`, `ICON_NAMES`, `render_icon(name, fill=False)` defined in Task 1 are used verbatim in Tasks 2–3 and the tests. Sprite symbol ids (`#i-<name>`, `#i-house-fill`) match between generator, sprite, template markup, and tests. Token names (`--accent`, `--accent-gradient`, `--chrome-bg`, `--surface`, `--canvas`, `--radius-lg`, `--elev-card`, `--dur`) are consistent across Tasks 4–5 and tests.

---

## Execution Handoff

(See the parent session — choose subagent-driven or inline execution.)
