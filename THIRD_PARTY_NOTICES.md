# Third-party notices

Mold3D itself is MIT licensed (see LICENSE). It builds on, calls, or was inspired by the projects below.
**No model weights, no third-party source trees, and no third-party datasets are bundled in this repository.**

## Code incorporated into this repository

### earthtojake/text-to-cad (MIT)
- Project: https://github.com/earthtojake/text-to-cad (an agent plugin of CAD skills on a `cadgen` runtime)
- **Adapted file:** `lib/step_parts.py` is adapted from `skills/step-parts/scripts/download_step_part.py` (default output directory changed, default `--limit` changed, stdlib-only; STEP->STL conversion lives in `forge step2stl`). It talks only to the read-only https://api.step.parts catalog and verifies each downloaded STEP against the catalog's sha256.
- **Ideas re-implemented from scratch (no code copied):** `lib/topo.py` (addressable solids/faces/edges + plain-English feature list), `lib/b123d_checks.py` (overlap volume, closest points, per-solid signed volume, B-rep soundness gate), the axis-aligned orientation ranking in `lib/verify_lib.py` (`verify --orient`), per-body wall thickness, and the units-suspect flag. See `reference/text-to-cad-review.md` for the full comparison and what was deliberately not adopted.
- The text-to-cad project is credited here under its MIT license. The upstream notice reads:

```
MIT License

Copyright (c) 2026 Thompson Labs LLC

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

(Standard MIT text reproduced with the upstream copyright holder named in the adapted file's header. If you redistribute, please check the upstream repository's LICENSE file for its authoritative wording.)

## Runtime dependencies (installed by you via pip, not redistributed here)
| project | use | license (check upstream) |
|---|---|---|
| build123d + OCP (OpenCascade) | b123d lane, STEP | Apache-2.0 (build123d); OpenCascade is LGPL-2.1 with exception |
| trimesh, numpy, scipy, scikit-image, shapely, networkx, Pillow | mesh + math | MIT / BSD / similar |
| manifold3d | exact mesh booleans | Apache-2.0 |
| usd-core | USDZ export for AR | Apache-2.0-style (Tomorrow Open Source Technology License) |
| OpenCV | photofit (ArUco) | Apache-2.0 |
| fogleman/sdf | SDF organic lane (`lib/sculpt.py`) | MIT |
| Blender (bpy, optional) | renders, showcase videos, bpy lane | GPL-3.0 (called as a separate program) |
| OpenSCAD (optional) | scad lane | GPL-2.0+ (called as a separate program) |

## Models used by `forge text3d` / `forge looks` (NOT bundled; downloaded by you on first run)
These are fetched from Hugging Face / GitHub by the libraries at runtime and stay under their own licenses and acceptable-use terms. You are responsible for reading and complying with them, especially before selling anything you generate.
| model | role | license |
|---|---|---|
| SimianLuo/LCM_Dreamshaper_v7 | fast text-to-image concept drawing | see its model card / license |
| Tencent Hunyuan3D-2mini (and 2mv) via the Tencent-Hunyuan/Hunyuan3D-2 source (you clone it yourself into `lib/text3d/Hunyuan3D-2`) | image-to-3D shape | Tencent Hunyuan community license: **see its license** (it carries territory and usage limits) |
| openai/clip-vit-base-patch32 | Looks Score (recognizability) | see its model card / license |
| rembg (isnet-general-use) | background removal | see the rembg project license |

Models you download from sites like Printables/Thingiverse and remix with `forge remix` keep their own licenses (CC BY-NC means no selling).

## Benchmark data
The benchmark compares against STEP files from the step.parts catalog and designs from Printables. Those files are **not** redistributed here; the write-up in `knowledge/benchmark-2026-10-17.md` contains only the numbers.

## Research references
`reference/sources.md` lists web pages, forum threads and videos consulted while writing the guidance; they are cited, not copied.
