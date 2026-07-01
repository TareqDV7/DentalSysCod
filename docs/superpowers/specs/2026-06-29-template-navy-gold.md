# Navy & Gold Endodontic Template — Design Specification

A polished, medical-professional template using a deep navy background with
muted gold accents. Originally built for a 1080×1080 Instagram post, but
fully tokenized below so it can drive any UI surface (web dashboard, print,
slide deck, etc.).

---

## 1. Canvas

| Property        | Value                          | Notes                          |
|-----------------|--------------------------------|--------------------------------|
| Base canvas     | `1080 × 1080 px` (1:1)         | Instagram square reference     |
| Working unit    | `1 px @ 1080 wide`             | Scale linearly for other sizes |
| Color space     | sRGB                            |                                |
| Background      | Radial gradient (`navy-mid` → `navy-deep`) centered at `(50%, 44%)` |

---

## 2. Color Tokens

| Token              | HEX        | RGB              | Usage                              |
|--------------------|------------|------------------|------------------------------------|
| `--color-navy-deep`  | `#040E20`  | `4, 14, 32`      | Outer background, edges            |
| `--color-navy-mid`   | `#0C1E3A`  | `12, 30, 58`     | Background center / radial bloom   |
| `--color-navy-panel` | `#08162C`  | `8, 22, 44`      | Cards, raised surfaces             |
| `--color-gold`       | `#C6A274`  | `198, 162, 116`  | Primary accent, borders, headings  |
| `--color-gold-light` | `#E0C498`  | `224, 196, 152`  | Hover, highlight                   |
| `--color-gold-deep`  | `#A08056`  | `160, 128, 86`   | Pressed / shadow gold              |
| `--color-text`       | `#F5F5F0`  | `245, 245, 240`  | Primary text on navy               |
| `--color-text-muted` | `#D2D7E1`  | `210, 215, 225`  | Secondary text                     |

**Gradient — page background**

```
radial-gradient(
  circle at 50% 44%,
  var(--color-navy-mid) 0%,
  var(--color-navy-deep) 100%
)
```

---

## 3. Typography

Family: **Poppins** (Google Font). Fallback: `system-ui, -apple-system, "Segoe UI", sans-serif`.

| Role             | Weight   | Size @ 1080px canvas | Color   | Tracking |
|------------------|----------|---------------------|---------|----------|
| Title — primary  | 700 Bold | `78 px`             | text    | normal   |
| Title — accent   | 700 Bold | `58 px`             | gold    | normal   |
| Section heading  | 700 Bold | `52 px`             | gold    | normal   |
| Body / labels    | 400 Reg  | `20 px`             | text    | normal   |
| Numerals (UI)    | 700 Bold | `19 px`             | text    | normal   |
| Caption          | 400 Reg  | `16 px`             | muted   | normal   |

**Convention:** the title is a two-line pair — the main descriptor in white
on top, a one-line qualifier in gold below. Center both lines on the canvas.

---

## 4. Layout Grid (for the 1080² template)

```
y =   0 ┌───────────────────────────────────────────────┐
        │                                               │
y = 130 │           « Title — primary (white) »         │  anchor: middle
y = 215 │           « Title — accent (gold) »           │  anchor: middle
y = 290 │   ─────── 🦷 ───────  (gold divider+icon)     │
        │                                               │
y = 360 │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐              │  4 panels
        │  │ X-1 │ │ X-2 │ │ X-3 │ │ X-4 │  h = 320     │
y = 680 │  └─────┘ └─────┘ └─────┘ └─────┘              │
y = 708 │  [pill] [pill] [    pill spans 2     ]        │  h = 56
        │                                               │
y = 920 │           « DR. WASFY BARZAQ »                │  gold, anchor mm
        │                                               │
y = 985 │   ∿∿∿∿∿  subtle gold wave lines  ∿∿∿∿∿        │
y =1080 └───────────────────────────────────────────────┘
```

| Region                     | x / y                         | width × height |
|----------------------------|-------------------------------|----------------|
| Outer side margin          | `16 px`                       | —              |
| Title block (line 1 mid-y) | y = 130                       | —              |
| Title block (line 2 mid-y) | y = 215                       | —              |
| Divider y-axis             | y = 290                       | —              |
| Divider side lines         | x = `18% → tooth - 16`, `tooth + 16 → 82%` | stroke 2 px |
| Tooth icon size            | 44 px tall, ~35 wide          | centered       |
| Panel row                  | y = 360                       | 250 × 320 each |
| Panel gap                  | 16 px horizontal              | —              |
| Pill row                   | y = panel_y + 348 (=708)      | h = 56         |
| Doctor name mid-y          | y = 920                       | —              |
| Wave band                  | y = 985 – 1050                | 3 layered sines|

> **Responsive rule:** multiply every px value by `(targetWidth / 1080)` when
> targeting a non-square or differently-sized surface.

---

## 5. Components

### 5.1 X-Ray Panel

| Property         | Value                                                      |
|------------------|------------------------------------------------------------|
| Aspect           | `250 : 320` (≈ 0.78 : 1)                                   |
| Corner radius    | `14 px` @ 1080 canvas                                      |
| Border           | Single `1 px` line, `var(--color-gold)` at 92% opacity     |
| Background       | Underlying X-ray content, no overlay                       |
| Shadow           | None — relies on gold rim for separation                   |

```css
.panel {
  width: 250px;
  height: 320px;
  border-radius: 14px;
  border: 1px solid rgba(198, 162, 116, 0.92);
  overflow: hidden;
}
```

### 5.2 Label Pill

```
┌──────────────────────────────────────────────┐
│   ╭───╮                                      │
│   │ 1 │   Before Treatment                   │
│   ╰───╯                                      │
└──────────────────────────────────────────────┘
```

| Property                  | Value                                          |
|---------------------------|------------------------------------------------|
| Height                    | `56 px`                                        |
| Width — single panel pill | `250 px`                                       |
| Width — double panel pill | `516 px` (= 2 × 250 + 16 gap)                  |
| Border radius             | full pill — `h/2` (= 28 px)                    |
| Border                    | `2 px` `var(--color-gold)` @ 86% opacity       |
| Inner circle (number)     | `26 px` diameter, `2 px` gold outline          |
| Circle x-offset           | `cx = h/2 + 2` from pill's left edge           |
| Text — single-panel pill  | Left-aligned, starts `cx + circle_radius + 10` |
| Text — double-panel pill  | **Centered** between circle and right edge     |
| Text style                | Poppins Regular, `20 px`, white                |
| Number style              | Poppins Bold, `19 px`, white                   |

### 5.3 Divider

```
─────────────── 🦷 ───────────────
```

* Two horizontal `2 px` gold lines @ 86% opacity.
* Left line:  `x: 18% → toothLeft - 16 px`
* Right line: `x: toothRight + 16 px → 82%`
* Tooth icon centered on canvas, 44 px tall.

### 5.4 Tooth Icon

* Source: vector molar outline (provided as `tooth_icon.svg` / extracted PNG).
* Stroke only, no fill, color = `var(--color-gold)`.
* Two-rooted lower molar — used as a brand mark in dividers and signatures.

### 5.5 Doctor / Brand Signature

| Property      | Value                                |
|---------------|--------------------------------------|
| Text          | `DR. WASFY BARZAQ` (uppercase)       |
| Font          | Poppins Bold `52 px`                 |
| Color         | `var(--color-gold)`                  |
| Position      | Bottom-centered, y ≈ 85% of canvas   |

### 5.6 Wave Footer (decorative)

Three layered low-amplitude sine waves at the very bottom in subtle gold:

| Layer | Amplitude | Frequency | Stroke alpha | y-offset |
|-------|-----------|-----------|--------------|----------|
| 1     | 14 px     | 0.012     | 38 / 255     | 985      |
| 2     | 18 px     | 0.009     | 30 / 255     | 1015     |
| 3     | 11 px     | 0.015     | 22 / 255     | 1045     |

All strokes: `2 px`, color `var(--color-gold)`.

---

## 6. CSS Variables — drop-in

```css
:root {
  /* color */
  --color-navy-deep:  #040E20;
  --color-navy-mid:   #0C1E3A;
  --color-navy-panel: #08162C;
  --color-gold:       #C6A274;
  --color-gold-light: #E0C498;
  --color-gold-deep:  #A08056;
  --color-text:       #F5F5F0;
  --color-text-muted: #D2D7E1;

  /* typography */
  --font-sans: "Poppins", system-ui, -apple-system, sans-serif;
  --fs-title:     78px;
  --fs-subtitle:  58px;
  --fs-heading:   52px;
  --fs-body:      20px;
  --fs-numeral:   19px;
  --fs-caption:   16px;

  /* radius */
  --radius-panel: 14px;
  --radius-pill:  9999px;

  /* spacing (gap between panels) */
  --gap-panel: 16px;
}

body {
  background:
    radial-gradient(circle at 50% 44%,
      var(--color-navy-mid) 0%,
      var(--color-navy-deep) 100%);
  color: var(--color-text);
  font-family: var(--font-sans);
}
```

---

## 7. Tailwind Config Snippet

```js
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        navy: {
          deep:  "#040E20",
          mid:   "#0C1E3A",
          panel: "#08162C",
        },
        gold: {
          DEFAULT: "#C6A274",
          light:   "#E0C498",
          deep:    "#A08056",
        },
        ink: {
          DEFAULT: "#F5F5F0",
          muted:   "#D2D7E1",
        },
      },
      fontFamily: {
        sans: ['Poppins', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        title:    ['78px', { lineHeight: '1.1', fontWeight: '700' }],
        subtitle: ['58px', { lineHeight: '1.15', fontWeight: '700' }],
        heading:  ['52px', { lineHeight: '1.2',  fontWeight: '700' }],
        body:     ['20px', { lineHeight: '1.4',  fontWeight: '400' }],
        numeral:  ['19px', { lineHeight: '1',    fontWeight: '700' }],
        caption:  ['16px', { lineHeight: '1.3',  fontWeight: '400' }],
      },
      borderRadius: {
        panel: '14px',
      },
      backgroundImage: {
        'navy-radial':
          'radial-gradient(circle at 50% 44%, #0C1E3A 0%, #040E20 100%)',
      },
    },
  },
};
```

---

## 8. JSON Design Tokens (W3C draft format)

```json
{
  "color": {
    "navy":  { "deep":  { "$value": "#040E20" },
               "mid":   { "$value": "#0C1E3A" },
               "panel": { "$value": "#08162C" } },
    "gold":  { "base":  { "$value": "#C6A274" },
               "light": { "$value": "#E0C498" },
               "deep":  { "$value": "#A08056" } },
    "text":  { "base":  { "$value": "#F5F5F0" },
               "muted": { "$value": "#D2D7E1" } }
  },
  "font": {
    "family": { "$value": "Poppins, system-ui, sans-serif" },
    "size": {
      "title":    { "$value": "78px" },
      "subtitle": { "$value": "58px" },
      "heading":  { "$value": "52px" },
      "body":     { "$value": "20px" },
      "numeral":  { "$value": "19px" },
      "caption":  { "$value": "16px" }
    },
    "weight": {
      "regular": { "$value": 400 },
      "bold":    { "$value": 700 }
    }
  },
  "radius": {
    "panel": { "$value": "14px" },
    "pill":  { "$value": "9999px" }
  },
  "spacing": {
    "panel-gap": { "$value": "16px" },
    "page-pad":  { "$value": "16px" }
  }
}
```

---

## 9. Usage Guidelines

1. **Title contract** — main descriptor in white; one-line qualifier in gold below. Don't reverse.
2. **Single accent color** — gold is the only accent. Avoid introducing reds/greens/blues except for X-ray content itself.
3. **Cards over gradients** — use `--color-navy-panel` for any card surface; the radial gradient is reserved for the page background.
4. **Pill text alignment** — left-align next to the circle for short text; center it inside a wide pill that spans multiple panels.
5. **Iconography** — line icons only, gold stroke, never filled. The tooth glyph is the brand mark and should be the only icon in the divider region.
6. **Density** — generous whitespace; never crowd the gold accents.
7. **Image rim** — every embedded medical image gets a single thin gold rim at the panel radius (`14px`).

---

## 10. File Outputs from the Reference Build

| File                            | Purpose                          |
|---------------------------------|----------------------------------|
| `endodontic_case_study_blue_gold.png` | 1080×1080 finished post     |
| `tooth_icon_clean.png`          | Brand mark, RGBA                 |
| `compose.py`                    | Reproducible build script        |

---

*Spec version:* 1.0 — Navy & Gold Endodontic
