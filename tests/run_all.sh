#!/usr/bin/env bash
# forge smoke tests (~30 s). Needs Blender (bpy lane + renders) and OpenSCAD (scad lane); a/b/c fail without them, the rest are pure python.
# Set FORGE_CAD_PY to your CAD venv python (default: <skill>/.venv-cad).
. "$(dirname "$0")/env.sh"; T="$F/tests/parts"; B="$F/bin"
pass=0; fail=0
t() { # t <label> <expected-rc> <cmd...>
  local label="$1" want="$2"; shift 2
  "$@" > "$F/tests/last_$$.log" 2>&1; local rc=$?
  if [ "$rc" = "$want" ]; then echo "PASS  $label (rc=$rc)"; pass=$((pass+1))
  else echo "FAIL  $label (rc=$rc, wanted $want)"; tail -15 "$F/tests/last_$$.log"; fail=$((fail+1)); fi
  rm -f "$F/tests/last_$$.log"
}
mk() { echo "$2" > "$F/tests/$1"; echo "$F/tests/$1"; }

# (a) bpy lane: tray + lid
SPEC_A=$(mk spec_tray.json '{"bbox_mm":[130,40,25],"components":2,"must_be_watertight":true}')
t "a. bpy tray+lid builds, verifies, renders" 0 "$B/forge" run "$T/tray_lid.py" --name t_tray_lid --spec "$SPEC_A"
# (b) build123d lane
SPEC_B=$(mk spec_box.json '{"bbox_mm":[40,30,20],"bbox_tol":0.3,"components":1,"min_wall_mm":1.5,"max_support_pct":10}')
t "b. build123d box w/ hole+fillets" 0 "$B/forge" run "$T/box_b123d.py" --name t_box --spec "$SPEC_B" --section z=10
# (c) scad lane
SPEC_C=$(mk spec_peg.json '{"bbox_mm":[30,30,14],"components":1}')
t "c. openscad plate+peg" 0 "$B/forge" run "$T/peg_scad.scad" --name t_peg --spec "$SPEC_C"
# (d) assembly: tray+lid seated with 0.3 clearance -> PASS; interference -> FAIL
P="$F/out/t_tray_lid/parts"
t "d1. assembly tray+lid @0.3 clearance PASS" 0 "$B/verify" --assembly "$P/tray.stl" "$P/lid.stl" --clearance 0.3 --move-b=-70,0,22
t "d2. assembly lid shifted 0.8mm into wall FAILS" 1 "$B/verify" --assembly "$P/tray.stl" "$P/lid.stl" --clearance 0.3 --move-b=-69.2,0,22
t "d3. assembly demands 0.5 clearance, has 0.3 -> FAILS" 1 "$B/verify" --assembly "$P/tray.stl" "$P/lid.stl" --clearance 0.5 --move-b=-70,0,22
# (e) verify must FAIL on bad inputs (generated with trimesh)
PY="$CAD"; D="$F/tests/bad"; mkdir -p "$D"
"$PY" - "$D" <<'PYEOF'
import sys, trimesh, numpy as np
d = sys.argv[1]
b = trimesh.creation.box([40, 30, 20]); b.apply_translation([0, 0, 10]); b.export(f"{d}/ok.stl")
o = b.copy(); o.update_faces(np.arange(len(o.faces))[1:]); o.export(f"{d}/open.stl")
t = trimesh.creation.box([10, 10, 10]); t.apply_translation([50, 0, 5]); trimesh.util.concatenate([b, t]).export(f"{d}/two.stl")
p = trimesh.creation.box([40, 30, 0.6]); p.apply_translation([0, 0, 0.3]); p.export(f"{d}/thin.stl")
g = trimesh.creation.box([300, 50, 10]); g.apply_translation([0, 0, 5]); g.export(f"{d}/big.stl")
i = b.copy(); i.invert(); i.export(f"{d}/inverted.stl")
post = trimesh.creation.box([10, 10, 20]); post.apply_translation([0, 0, 10]); slab = trimesh.creation.box([40, 30, 5]); slab.apply_translation([0, 0, 22.5])
trimesh.boolean.union([post, slab], engine="manifold").export(f"{d}/tshape.stl") if False else trimesh.util.concatenate([post, slab]).export(f"{d}/tshape.stl")
PYEOF
SPEC_W=$(mk spec_wall.json '{"min_wall_mm":1.2}'); SPEC_S=$(mk spec_sup.json '{"max_support_pct":5,"components":2}')
t "e0. sane box verifies PASS" 0 "$B/verify" "$D/ok.stl"
t "e1. non-watertight FAILS" 1 "$B/verify" "$D/open.stl"
t "e2. two floating bodies FAILS" 1 "$B/verify" "$D/two.stl"
t "e3. 0.6mm wall FAILS with min_wall spec" 1 "$B/verify" "$D/thin.stl" --spec "$SPEC_W"
t "e4. too big for bed FAILS" 1 "$B/verify" "$D/big.stl"
t "e5. inverted normals FAILS" 1 "$B/verify" "$D/inverted.stl"
t "e6. wrong bbox vs spec FAILS" 1 "$B/verify" "$D/ok.stl" --spec <(echo '{"bbox_mm":[50,30,20]}')
t "e7. T-shape overhang -> support limit FAILS" 1 "$B/verify" "$D/tshape.stl" --spec "$SPEC_S"
t "e8. missing file errors (rc=2)" 2 "$B/verify" "$D/nope.stl"

# (f) text-to-cad merge: topo ids/features, orientation ranking, b123d_checks, step2stl, per-body walls
CADPY="$CAD"
"$CADPY" - "$D/p.step" <<'PYEOF'
import sys
from build123d import *
b = Box(60,40,25,align=(Align.CENTER,Align.CENTER,Align.MIN)) - Pos(0,0,2.4)*Box(55,35,30,align=(Align.CENTER,Align.CENTER,Align.MIN))
b = b - [Pos(x,y,-1)*Cylinder(1.7,5,align=(Align.CENTER,Align.CENTER,Align.MIN)) for x in (-20,20) for y in (-10,10)]
export_step(b, sys.argv[1])
PYEOF
t "f1. topo lists 4 holes dia 3.4" 0 bash -c "'$B/forge' topo '$D/p.step' | grep -c 'dia 3.4 mm' | grep -qx 4"
t "f2. topo --near finds a hole face" 0 bash -c "'$B/forge' topo '$D/p.step' --near=-20,-10,1 | head -3 | grep -q hole"
t "f3. verify --orient puts T-shape upside down" 0 bash -c "'$B/verify' --orient '$D/tshape.stl' | grep -q 'flip_180_x (upside down).*recommended'"
t "f4. b123d_checks: overlap/None-safe, assert_solid catches 2 solids" 0 "$CADPY" -c "
import sys; sys.path.insert(0,'$F/lib')
from build123d import *; from b123d_checks import *
a=Box(10,10,10); far=Pos(30,0,0)*Box(10,10,10)
assert overlap_volume(a,far)==0.0 and abs(overlap_volume(a,Pos(5,0,0)*Box(10,10,10))-500)<1e-3 and abs(min_distance(a,far)-20)<1e-6
try: assert_solid(a+far); sys.exit(1)
except AssertionError: pass
assert_solid(a)"
t "f5. step2stl round-trips a STEP" 0 bash -c "'$B/forge' step2stl '$D/p.step' '$D/p.stl' && '$B/verify' '$D/p.stl' --spec <(echo '{\"bbox_mm\":[60,40,25],\"bbox_tol\":0.2}')"
t "f6. two bodies are walled per-body (no gap-as-wall)" 0 bash -c "'$B/verify' '$D/two.stl' --spec <(echo '{\"components\":2,\"min_wall_mm\":1.2}') | grep -q 'per body'"

# (g) auto-support trap + 3MF export through the real CLI: two bodies 0.3 mm apart (flat lid over a slab) -> trap; the 3MF says supports OFF
"$CADPY" - "$D" <<'PYEOF'
import sys, trimesh
d = sys.argv[1]
slab = trimesh.creation.box([40, 40, 10]); slab.apply_translation([0, 0, 5]); lid = trimesh.creation.box([20, 20, 4]); lid.apply_translation([0, 0, 12.3])
trimesh.util.concatenate([slab, lid]).export(f"{d}/trap_float.stl")          # lid floats in mid-air: needs supports AND supports weld -> NO-GO
hole = trimesh.creation.box([7, 7, 12]); hole.apply_translation([0, 0, 5]); slab = trimesh.boolean.difference([slab, hole], engine="manifold")
pin = trimesh.creation.box([6, 6, 14.3]); pin.apply_translation([0, 0, 7.15]); cap = trimesh.creation.box([10, 10, 4]); cap.apply_translation([0, 0, 12.3])
trimesh.util.concatenate([slab, trimesh.boolean.union([pin, cap], engine="manifold")]).export(f"{d}/trap2.stl")   # pin through the slab, cap 0.3 mm over it
PYEOF
t "g1. preflight flags the 0.3 mm flat bridge over another body" 0 bash -c "'$B/forge' preflight '$D/trap2.stl' | grep -q 'auto supports would fill the 0.30 mm gap'"
t "g2. forge export writes *_SUPPORTS-OFF.3mf with enable_support 0" 0 bash -c "'$B/forge' export '$D/trap2.stl' --no-orca >/dev/null; unzip -p '$D/trap2_SUPPORTS-OFF.3mf' Metadata/project_settings.config | grep -q '\"enable_support\": \"0\"'"
t "g2b. a lid that floats over a slab needs supports AND supports weld: export auto refuses (NO-GO)" 1 "$B/forge" export "$D/trap_float.stl" --no-orca
t "g3. forge export of a single-body box (auto) -> SUPPORTS-OFF too, no trap" 0 bash -c "'$B/forge' export '$D/ok.stl' --no-orca | grep -q 'supports OFF' && ! '$B/forge' preflight '$D/ok.stl' | grep -q TRAP"
if [ -n "$FORGE_TEST_NET" ]; then t "f7. parts-find (needs network)" 0 bash -c "'$B/forge' parts-find 'M3 socket head 12' --limit 2 | grep -q iso4762"; fi
rm -f "$F"/tests/spec_*.json
echo; echo "RESULT: $pass passed, $fail failed"
[ "$fail" = 0 ]
