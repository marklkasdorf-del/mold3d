#!/usr/bin/env bash
# forge text3d "<idea>" [--height 55] [--base "NAME"|--no-base] [--flexi] [--helmet [--head 160,190]] [--n 4] [--seed 1] [--thicken 0.3] [--out DIR]
#
# Words -> printed object, 100% local + free (needs Blender + a GPU/MPS/CUDA/CPU torch; run outside agent sandboxes):
#   1 concept   LCM-Dreamshaper-v7 draws n 3D-friendly candidates, CLIP + cut-out score picks the best   (~30 s)
#   2 shape     Hunyuan3D-2mini turns the picked image into a mesh on your GPU (Apple MPS / CUDA / CPU)                     (~2.5 min)
#   3 printable figure_post: watertight remesh, smooth, scale, flat base, optional name plinth           (~10 s)
#   4 flexi     (--flexi) top-view concept -> outline relief (relief.py) -> flexify adds print-in-place joints
#     helmet    (--helmet) helmet-only prompt, Hunyuan at res 320, helmet_post: neck cut, sized to a head you specify, 3 mm shell,
#               faceplate split + 4 magnet bosses, both pieces posed seam-down and sliced
#   5 check     preflight (verdict + supports decision) + renders + slice stats via your slicer hook (time, grams)
# Licenses: weights are NOT bundled; you download them. LCM-Dreamshaper and Hunyuan3D-2mini have their own licenses (Hunyuan: Tencent community license, with territory/usage terms) -> read them before selling. See THIRD_PARTY_NOTICES.md.
set -euo pipefail
L="$(cd "$(dirname "$0")/.." && pwd)"; F="$(cd "$L/.." && pwd)"
# interpreters: FORGE_AI_PY (torch/diffusers; default <skill>/.venv-ai) and FORGE_CAD_PY (build123d/trimesh; default <skill>/.venv-cad)
HG="${FORGE_AI_PY:-$F/.venv-ai/bin/python}"; CAD="${FORGE_CAD_PY:-$F/.venv-cad/bin/python}"
[ -x "$HG" ] || { echo "text3d: AI python not found ($HG). python3.12 -m venv .venv-ai && .venv-ai/bin/pip install -r requirements-ai.txt (or set FORGE_AI_PY)" >&2; exit 3; }
[ -x "$CAD" ] || CAD="$(command -v python3)"
[ -d "$L/text3d/Hunyuan3D-2" ] || { echo "text3d: Hunyuan3D-2 source not found. git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2 $L/text3d/Hunyuan3D-2 (see README)" >&2; exit 3; }
slice_hook() {  # slice_hook <stl> <supports>: runs your slicer command if configured; prints time/grams lines
  local cmd="${FORGE_SLICER_CMD:-}"; [ -n "$cmd" ] || cmd=$("$CAD" -c "import sys;sys.path.insert(0,'$L');import printer;print(printer.get('slicer_cmd'))" 2>/dev/null || true)
  [ -n "$cmd" ] || { echo "(no slicer hook set: slice $1 in your own slicer, supports=$2)"; return 0; }
  cmd="${cmd//\{stl\}/$1}"; cmd="${cmd//\{supports\}/$2}"; bash -c "$cmd" 2>&1 | grep -E "printing time|total filament used \[g\]" || true
}
export PYTORCH_ENABLE_MPS_FALLBACK=1
[ $# -ge 1 ] || { sed -n 2,12p "$0"; exit 2; }
IDEA="$1"; shift
HEIGHT=55; BASE=""; NOBASE=0; FLEXI=0; HELMET=0; HEAD="160,190"; N=4; SEED=1; THICK=0; OUT=""
while [ $# -gt 0 ]; do case "$1" in
  --height) HEIGHT="$2"; shift 2;; --base) BASE="$2"; shift 2;; --no-base) NOBASE=1; shift;;
  --flexi) FLEXI=1; shift;; --helmet) HELMET=1; N=6; shift;; --head) HEAD="$2"; shift 2;;
  --n) N="$2"; shift 2;; --seed) SEED="$2"; shift 2;;
  --thicken) THICK="$2"; shift 2;; --out) OUT="$2"; shift 2;; *) echo "unknown arg $1"; exit 2;; esac; done
SLUG=$(echo "$IDEA" | tr 'A-Z' 'a-z' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//' | cut -c1-40)
[ $FLEXI = 1 ] && SLUG="$SLUG-flexi"
OUT="${OUT:-$F/out/text3d/$SLUG}"; mkdir -p "$OUT"
T0=$(date +%s)
VIEW=front; [ $FLEXI = 1 ] && VIEW=top
if [ $HELMET = 1 ]; then
  P="a single $IDEA, product photo, helmet only, no person, no body, no shoulders, three-quarter front view, isolated on a plain white background, smooth matte grey 3D render, soft studio light"
  echo "[1/5] concept ($N helmet candidates)"; "$HG" "$L/text3d/concept.py" "$P" "$OUT" --n "$N" --seed "$SEED" --raw-prompt 2>/dev/null | tail -1
  echo "[2/5] shape (Hunyuan3D-2mini, res 320)"; HY_STEPS=50 HY_RES=320 HY_DTYPE=float16 "$HG" "$L/text3d/hy3d_run.py" "$OUT/raw.glb" "$OUT/concept.png" 2>/dev/null | grep -E "^gen|^loaded" || true
  echo "[3/5] wearable: neck cut, head fit $HEAD, 3 mm shell, faceplate + magnets"; "$CAD" "$L/text3d/helmet_post.py" "$OUT/raw.glb" "$OUT" --head "$HEAD" | tail -3
  echo "[4/5] print poses (seam on the bed)"
  "$CAD" -c "
import trimesh, numpy as np
for nm, ang in (('shell', 90), ('faceplate', -90)):
    t = trimesh.load('$OUT/helmet_' + nm + '.stl'); t.apply_transform(trimesh.transformations.rotation_matrix(np.radians(ang), [1, 0, 0]))
    t.apply_translation([-t.bounds.mean(0)[0], -t.bounds.mean(0)[1], -t.bounds[0][2]]); t.export('$OUT/print_' + nm + '.stl')"
  echo "[5/5] check + slice"; "$F/bin/render" "$OUT/helmet_assembled.stl" "$OUT/r" >/dev/null 2>&1 || true
  for nm in shell faceplate; do "$CAD" "$L/preflight.py" "$OUT/print_$nm.stl" | head -1
    slice_hook "$OUT/print_$nm.stl" auto; done
  echo "DONE in $(( $(date +%s) - T0 )) s -> $OUT (helmet_shell.stl, helmet_faceplate.stl, print_*.stl, helmet.json)"; exit 0
fi
echo "[1/5] concept ($N candidates, $VIEW view)"; "$HG" "$L/text3d/concept.py" "$IDEA" "$OUT" --n "$N" --seed "$SEED" --view "$VIEW" 2>/dev/null | tail -1
[ $FLEXI = 1 ] || echo "[2/5] shape (Hunyuan3D-2mini)"; [ $FLEXI = 1 ] || HY_STEPS=40 HY_RES=256 HY_DTYPE=float16 "$HG" "$L/text3d/hy3d_run.py" "$OUT/raw.glb" "$OUT/concept.png" 2>/dev/null | grep -E "^gen|^loaded" || true
NAME="${BASE:-$(echo "$IDEA" | tr 'a-z' 'A-Z' | cut -c1-14)}"
if [ $FLEXI = 1 ]; then
  echo "[3/5] outline relief (${HEIGHT} mm long, 9 mm tall; top views make blobs in image->3D, so no Hunyuan here)"
  "$CAD" "$L/text3d/relief.py" "$OUT/concept.png" "$OUT/flat.stl" --length "$HEIGHT" --thick 9 | tail -1
  echo "[4/5] flexify"; "$CAD" "$L/flexify.py" "$OUT/flat.stl" --out "$OUT/flexi" --name "$SLUG" --spacing 12 | head -1
  FINAL="$OUT/flexi/$SLUG.stl"
else
  echo "[3/5] printable (${HEIGHT} mm tall)"
  if [ $NOBASE = 1 ]; then "$CAD" "$L/text3d/figure_post.py" "$OUT/raw.glb" "$OUT/$SLUG.stl" --height "$HEIGHT" --thicken "$THICK" | tail -1
  else "$CAD" "$L/text3d/figure_post.py" "$OUT/raw.glb" "$OUT/$SLUG.stl" --height "$HEIGHT" --base "$NAME" --thicken "$THICK" | tail -1; fi
  FINAL="$OUT/$SLUG.stl"
fi
echo "[5/5] check"; "$CAD" "$L/preflight.py" "$FINAL" --json "$OUT/preflight.json" --heat "$OUT/heat.ply" || true
"$F/bin/render" "$FINAL" "$OUT/r" >/dev/null 2>&1 || true
"$F/bin/blender_py" "$L/heat_render.py" "$OUT/heat.ply" "$OUT/heat.png" >/dev/null 2>&1 || true
SUP=$("$CAD" -c "import json;print(json.load(open('$OUT/preflight.json')).get('supports','off'))" 2>/dev/null || echo auto)
slice_hook "$FINAL" "$SUP" | tee "$OUT/slice.txt" || true
echo "DONE in $(( $(date +%s) - T0 )) s -> $FINAL  (sheet: $OUT/r/sheet.png, candidates: $OUT/candidates_sheet.png, heat: $OUT/heat_iso.png)"
