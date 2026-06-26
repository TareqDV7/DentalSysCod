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
