"""Pure, Flask-free post-image composition engine."""
import arabic_reshaper
from bidi.algorithm import get_display
from collections import namedtuple
from dataclasses import dataclass
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from PIL import ImageOps
from post_themes import get_theme

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


def fit_crop(image, w, h):
    return ImageOps.fit(image.convert('RGB'), (w, h), method=Image.LANCZOS)


def is_rtl(text):
    return any('؀' <= ch <= 'ۿ' for ch in (text or ''))


def shape_arabic(text):
    if not is_rtl(text):
        return text
    return get_display(arabic_reshaper.reshape(text))


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


def _font(path: str, px: int):
    return ImageFont.truetype(path, px)


def _draw_text(draw, xy, text: str, font, fill, anchor: str = 'la') -> None:
    draw.text(xy, shape_arabic(text), font=font, fill=fill, anchor=anchor)


def _pick_font(theme, text: str, px: int, latin_path: str):
    """Arabic text needs the Arabic font; Manrope/Playfair render it as tofu."""
    path = theme.arabic_font if is_rtl(text) else latin_path
    return ImageFont.truetype(path, px)


def render_post(spec: PostSpec) -> Image.Image:
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
    name_font = _pick_font(theme, spec.doctor_name, int(header_h * 0.42), theme.heading_font)
    _draw_text(draw, (pad, header_h // 2), spec.doctor_name, name_font,
               theme.fg, anchor='lm')
    if spec.logo is not None:
        lh = int(header_h * 0.66)
        logo = fit_crop(spec.logo.convert('RGB'), lh, lh)
        canvas.paste(logo, (W - pad - lh, (header_h - lh) // 2))

    # Photo grid
    region = Rect(pad, header_h, W - 2 * pad, H - header_h - footer_h - pad)
    rects = photo_grid_rects(len(spec.photos), region)
    label_px = max(20, int(region.h * 0.045))
    for ph, r in zip(spec.photos, rects):
        canvas.paste(fit_crop(ph.image, r.w, r.h), (r.x, r.y))
        if ph.label:
            draw.rectangle([r.x, r.y + r.h - 44, r.x + r.w, r.y + r.h],
                           fill=theme.accent)
            _draw_text(draw, (r.x + r.w // 2, r.y + r.h - 22), ph.label,
                       _pick_font(theme, ph.label, label_px, theme.label_font),
                       theme.bg, anchor='mm')

    # Footer accent bar
    draw.rectangle([0, H - footer_h, W, H], fill=theme.accent)
    return canvas
