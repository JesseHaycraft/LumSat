# LumSat

A cross-platform desktop app for editing the **saturation-vs-luminance**
relationship of photos. You draw a curve — luminance on the X axis (0–100%),
a saturation multiplier on the Y axis (0–150%) — and LumSat boosts or cuts color
richness based on each pixel's brightness. Desaturate muddy shadows while
keeping highlights vivid, tame oversaturated skies, and more.

Runs on **Windows, macOS, and Linux** (Python + Qt).

## Features

- Import one or many photos (JPG, PNG, TIFF) and switch between them in a
  left-side filmstrip.
- Live center preview with mouse-wheel zoom and drag-to-pan.
- Interactive curve editor: click the curve to add a point, drag to reshape,
  double-click a point to delete it. Edits preview in real time.
- Perceptual color math (OKLab): saturation changes keep brightness and hue
  stable, avoiding the muddy or shifted look of naive HSV edits.
- 16-bit-precision internal pipeline to avoid banding in skies and gradients.
- Save the current curve as a named **preset**; apply a preset to the current
  image or to every loaded image at once.
- Export to JPG (quality, chroma subsampling), PNG (compression), or TIFF
  (8/16-bit, LZW/ZIP), for the current image or the whole batch. JPG/PNG follow
  web-sharing conventions: an embedded sRGB ICC profile, and progressive,
  optimized JPEGs (4:2:0 by default, with a 4:4:4 option for full color detail).

## How saturation editing works

For every pixel the engine:

1. Converts sRGB → OKLab (a perceptual color space).
2. Reads the pixel's perceptual lightness `L` and looks up a saturation
   multiplier for that luminance from your curve.
3. Scales the OKLab color axes (`a`/`b`) by that multiplier — which changes
   color richness while leaving lightness and hue untouched.
4. Converts back to sRGB.

A flat curve at 100% means "no change."

## Setup

Requires **Python 3.9+**.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Tests

The engine has headless tests (no GUI required):

```bash
python -m pytest tests/            # if pytest is installed
python tests/test_engine.py        # or run directly
```

## Project layout

```
main.py                 entry point
lumsat/
  app.py                QApplication + theme bootstrap
  theme.py              dark, unobtrusive stylesheet
  main_window.py        assembles the UI and wires up actions
  qt_util.py            numpy <-> QImage helpers
  models/
    curve.py            editable curve + monotone-cubic interpolation + LUT
    image_item.py       per-image state (pixels, proxy, thumbnail, curve)
    preset.py           load/save named curve presets as JSON
  processing/
    color.py            sRGB <-> linear <-> OKLab conversions
    pipeline.py         apply a curve to an image (OKLab chroma scaling)
    imageio.py          load/save JPG/PNG/TIFF, 8/16-bit handling
    worker.py           background threads for preview + export
  widgets/
    filmstrip.py        left thumbnail list
    preview_view.py     center pan/zoom preview
    curve_editor.py     bottom interactive curve editor
    options_panel.py    right-side actions + preset controls
    export_dialog.py    export options window
  presets/              bundled starter presets
tests/                  headless engine tests
```

## Packaging (optional)

To build standalone executables per OS, [PyInstaller](https://pyinstaller.org)
works well:

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --name LumSat \
  --add-data "lumsat/presets:lumsat/presets" main.py
```

(On Windows use `;` instead of `:` in `--add-data`.)

## Known limitations (v1)

- Extreme saturation boosts are hard-clipped to the sRGB gamut (no soft gamut
  compression yet).
- No camera RAW import. Input images are assumed to be sRGB (embedded input
  ICC profiles are not read); exports are tagged with an sRGB profile.
- Undo is limited to "Reset Curve."
