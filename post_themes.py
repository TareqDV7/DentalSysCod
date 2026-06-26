"""Theme palettes and font paths for the Post Studio engine."""
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


def get_theme(key: str) -> Theme:
    return THEMES_BY_KEY.get(key, THEMES_BY_KEY['clean_clinical'])
