import web_assets
from templates import HTML_TEMPLATE


def test_font_css_is_inlined_woff2_for_required_families():
    css = web_assets.FONT_FACE_CSS
    assert css.count("@font-face") >= 8, "expected >=8 @font-face blocks (5 Manrope + 3 Space Grotesk)"
    assert "data:font/woff2;base64," in css, "fonts must be base64-inlined, not linked"
    assert "fonts.googleapis.com" not in css and "url(http" not in css, "no remote URLs in font CSS"
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
    assert sprite.count("<path") >= len(web_assets.ICON_NAMES)


def test_render_icon_emits_use_reference():
    assert web_assets.render_icon("bell") == '<svg class="ic" aria-hidden="true"><use href="#i-bell"/></svg>'
    assert web_assets.render_icon("house", fill=True) == '<svg class="ic ic-fill" aria-hidden="true"><use href="#i-house-fill"/></svg>'


# --- Task 2: fonts self-hosted in the template (no Google CDN) ---


def test_template_has_no_google_fonts_cdn():
    assert "fonts.googleapis.com" not in HTML_TEMPLATE
    assert "fonts.gstatic.com" not in HTML_TEMPLATE


def test_template_inlines_self_hosted_fonts():
    assert "@font-face" in HTML_TEMPLATE
    assert "data:font/woff2;base64," in HTML_TEMPLATE
    # families still referenced by the UI
    assert "Space Grotesk" in HTML_TEMPLATE and "Manrope" in HTML_TEMPLATE


# --- Task 3: inline Phosphor icon sprite (offline, no CDN) ---


def test_template_embeds_icon_sprite():
    assert 'id="i-house"' in HTML_TEMPLATE and 'id="i-house-fill"' in HTML_TEMPLATE
    assert 'id="i-gear"' in HTML_TEMPLATE  # the icon the mockup broke — must be real
    assert "unpkg.com" not in HTML_TEMPLATE  # never the CDN webfont at runtime
    assert "@phosphor-icons/web" not in HTML_TEMPLATE
