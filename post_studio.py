"""Pure, Flask-free post-image composition engine."""
from collections import namedtuple
from dataclasses import dataclass

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
