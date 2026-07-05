"""Mirror static/post_studio/*.js into clinic_mobile_app/assets/post_studio/ for
the Flutter asset bundler (P6 mobile parity). static/post_studio/ stays the
single source of truth for the JS modules; mobile_editor.html is hand-written
and lives only under the Flutter assets folder. Run after editing any
static/post_studio/*.js file, before an APK/IPA build:
    python tools/sync_post_studio_mobile_assets.py
"""
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "static" / "post_studio"
DEST = ROOT / "clinic_mobile_app" / "assets" / "post_studio"

JS_MODULES = [
    "composition.js", "themes.js", "render.js", "rasterize.js",
    "fonts.js", "inspector.js", "editor.js", "host.js",
]


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for name in JS_MODULES:
        shutil.copyfile(SRC / name, DEST / name)
    print(f"synced {len(JS_MODULES)} modules to {DEST}")


if __name__ == "__main__":
    main()
