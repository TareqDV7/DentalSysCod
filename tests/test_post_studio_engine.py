import pytest
from PIL import Image
from post_studio import Rect, photo_grid_rects, fit_crop, is_rtl, shape_arabic


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
    # reshape + bidi must actually transform Arabic into presentation forms,
    # not return the input unchanged.
    assert isinstance(shaped, str) and shaped != '' and shaped != 'عيادة'


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


def test_render_handles_arabic_name_and_label():
    spec = PostSpec(photos=[Photo(Image.new('RGB', (200, 200), (80, 80, 80)), 'قبل')],
                    doctor_name='د. وصفي برزق', theme='dark_premium', size='square', logo=None)
    img = render_post(spec)           # exercises the Arabic-font path (no tofu)
    assert img.size == POST_SIZES['square']
