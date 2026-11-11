#!/usr/bin/env bash
# max-model regression suite (pure python/CAD stack, no Blender, no model weights). Every check has a KNOWN right answer.
# Self-contained: all inputs are generated here. Set FORGE_CAD_PY to your CAD venv python.
. "$(dirname "$0")/env.sh"; L="$F/lib"; T="$F/out/tests_v2"
mkdir -p "$T"; pass=0; fail=0
ok() { echo "PASS  $1"; pass=$((pass+1)); }
no() { echo "FAIL  $1  ($2)"; fail=$((fail+1)); }
cd "$L"

# 1 MechKit: every mechanism builds, sweeps clear, controls jam, gaps ~ pip_gap
if "$CAD" -m mechkit.cli test fitcard gyro balisong helix cycloidal > "$T/mech.log" 2>&1; then ok "mechkit fitcard/gyro/balisong/helix/cycloidal self-tests"; else no "mechkit" "see $T/mech.log"; fi

# 1b cycloid profile known answers: N=12 R=38 r_p=3 e=1.5 gap=0.3 -> 11 lobes, r_max 36.20 +-0.05, r_min >= 33.2, simple polygon;
#     an undercut (pin radius above the smallest convex radius of curvature, 12.3 mm here) and e >= R/N must raise
"$CAD" - <<'PY' && ok "cycloid profile: 11 lobes, r_max 36.20, r_min >= 33.2, simple; undercut + bad eccentricity raise" || no "cycloid profile" "known answers differ"
import sys; sys.path.insert(0, '.'); import cycloid
c = cycloid.checks(12, 38, 3, 1.5, 0.3)
assert c["valid"] and c["lobes"] == 11 and abs(c["r_max"] - 36.2) <= 0.05 and c["r_min"] >= 33.2 - 0.05 and not c["undercut"], c
for bad in (dict(r_p=12.5), dict(e=3.5)):
    try: cycloid.checks(**{**dict(N=12, R=38, r_p=3, e=1.5, gap=0.3), **bad}); sys.exit("did not raise: %s" % bad)
    except ValueError: pass
PY

# 1c measured ratio: planetary (ring/sun, mesh) = -zs/zr = -1/3 within 0.5 %, cyclo11 = -11.00 within 0.5 %, a wrong declared ratio -> exit 3
"$CAD" -m mechkit.cli ratio planetary --motion mesh --driven ring --driver sun --out "$T/pl_ratio" > "$T/ratio_pl.log" 2>&1
"$CAD" -c "import json,sys;r=json.load(open('$T/pl_ratio/ratio.json'));sys.exit(0 if abs(r['measured_out_per_in']+1/3)<0.005/3 else 1)" && ok "measured ratio planetary = $(grep -o 'out/in [^)]*' "$T/ratio_pl.log")" || no "ratio planetary" "see $T/ratio_pl.log"
"$CAD" -m mechkit.cli ratio cyclo11 --out "$T/cy_ratio" > "$T/ratio_cy.log" 2>&1
"$CAD" -c "import json,sys;r=json.load(open('$T/cy_ratio/ratio.json'));sys.exit(0 if abs(r['measured']+11)<0.055 else 1)" && ok "measured ratio cyclo11 = $("$CAD" -c "import json;print(json.load(open('$T/cy_ratio/ratio.json'))['measured'])"):1" || no "ratio cyclo11" "see $T/ratio_cy.log"
"$CAD" -m mechkit.cli ratio cyclo11 --declared 10 --out "$T/cy_ratio10" > /dev/null 2>&1; [ $? = 3 ] && ok "a wrong declared ratio (10 vs 11) is a mismatch (exit 3)" || no "ratio mismatch" "exit code not 3"

# 2 flexify: SDF gecko -> all joints pass, no floating pieces
"$CAD" sculpt.py "$T/gecko.stl" > /dev/null 2>&1
if "$CAD" flexify.py "$T/gecko.stl" --out "$T/gecko_flexi" --name gecko_flexi --spacing 11 2>&1 | head -1 | grep -q PASS; then ok "flexify gecko (all joints swing clear, pins capture)"; else no "flexify gecko" "run it by hand"; fi

# 3 preflight knows the classic failures
"$CAD" - "$T" <<'PY'
import sys; sys.path.insert(0, '.'); import meshkit as mk
from manifold3d import Manifold
o = sys.argv[1] + '/'
mk.save(Manifold.sphere(15, 96).translate([0, 0, 15]), o + 'sphere.stl')
mk.save(mk.box(-20,-5,0,-15,5,20) + mk.box(15,-5,0,20,5,20) + mk.box(-20,-5,18,20,5,20), o + 'bridge30.stl')
mk.save(mk.box(-10,-5,0,-5,5,20) + mk.box(5,-5,0,10,5,20) + mk.box(-10,-5,18,10,5,20), o + 'bridge10.stl')
mk.save(mk.box(-5,-5,0,5,5,20) + mk.box(12,-5,10,30,5,14), o + 'floating.stl')
PY
chk() { v=$("$CAD" preflight.py "$T/$1.stl" 2>/dev/null | head -1 | sed 's/^\[\([^]]*\)\].*/\1/'); [ "$v" = "$2" ] && ok "preflight $1 -> $2" || no "preflight $1" "got $v, want $2"; }
chk sphere NO-GO; chk bridge30 GO+SUPPORTS; chk bridge10 GO; chk floating GO+SUPPORTS

# 4 gridfinity: a 1x1x6 bin is 41.5 x 41.5 mm (42 grid - 0.5 clearance) and 6 x 7 mm + stacking lip tall (~45.8)
"$CAD" gridfinity.py bin 1 1 6 --magnets --out "$T/gf.stl" > /dev/null 2>&1
read gx gy gz < <("$CAD" -c "import trimesh;e=trimesh.load('$T/gf.stl').extents;print(*[round(float(v),1) for v in e])" 2>/dev/null)
python3 -c "import sys;sys.exit(0 if 41<=float('${gx:-0}')<=42.1 and 41<=float('${gy:-0}')<=42.1 and 44<=float('${gz:-0}')<=47 else 1)" && ok "gridfinity 1x1x6 bin is ${gx} x ${gy} x ${gz} mm" || no "gridfinity" "${gx} x ${gy} x ${gz}"

# 5 split: an oversized model -> every piece fits the bed (generated 3x-bed-length bar)
"$CAD" - "$T" <<'PY'
import sys; sys.path.insert(0, '.'); import meshkit as mk, printer
b = printer.bed()
mk.save(mk.box(0, 0, 0, b[0] * 2.2, 60, 40), sys.argv[1] + '/bigbar.stl')
PY
if "$CAD" split.py "$T/bigbar.stl" --out "$T/split" 2>/dev/null | grep -q "fits=False"; then no "split" "a piece does not fit"; else ls "$T/split"/*.stl >/dev/null 2>&1 && ok "split 2.2x-bed bar -> all pieces fit the bed" || no "split" "no output"; fi

# 6 AR export: real-world size survives the mm -> metre / Z-up -> Y-up conversion (gyro is 48.4 x 11 mm)
"$CAD" mechkit/cli.py build gyro --out "$T/gyro" > /dev/null 2>&1 || (cd "$L" && "$CAD" -m mechkit.cli build gyro --out "$T/gyro" > /dev/null 2>&1)
"$CAD" ar.py "$T/gyro/gyro.stl" --out "$T/gyro_ar" > /dev/null 2>&1
"$CAD" -c "
from pxr import Usd, UsdGeom; st = Usd.Stage.Open('$T/gyro_ar.usdz')
r = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default']).ComputeWorldBound(st.GetDefaultPrim()).GetRange(); s = r.GetMax() - r.GetMin()
import sys; sys.exit(0 if abs(s[0]-0.0484) < 0.001 and abs(s[1]-0.011) < 0.001 else 1)" 2>/dev/null && ok "AR usdz is real size (48.4 x 11 mm, Y-up)" || no "ar" "size/axes wrong (or usdz written elsewhere)"

# ---- FEATURES (remix / make / plate) on generated inputs
R="$T/remix"; mkdir -p "$R"
"$CAD" - "$R" <<'PY'
import sys; sys.path.insert(0, '.'); import meshkit as mk
from manifold3d import Manifold
o = sys.argv[1] + '/'
mk.save(mk.box(-20,-20,0,20,20,10), o + 'block40.stl')
# hollow box with 0.8 mm walls (thin on purpose)
mk.save(mk.box(-20,-20,0,20,20,30) - mk.box(-19.2,-19.2,0.8,19.2,19.2,31), o + 'thin_box.stl')
PY
g=$("$CAD" remix.py "$R/block40.stl" keychain --out "$R/key.stl" 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['genus_after']-d['genus_before'])")
[ "$g" = "1" ] && ok "remix keychain adds a real through-hole (genus +1)" || no "keychain" "genus delta $g"
w=$("$CAD" remix.py "$R/block40.stl" magnets --side bottom --count 3 --magnet 6x3 --out "$R/mag.stl" 2>/dev/null | python3 -c "import json,sys;m=json.load(sys.stdin)['magnets'];print(round(min(20-max(abs(c[0]),abs(c[1])) for c in m)-3.05,2))")
python3 -c "import sys; sys.exit(0 if float('$w') >= 1.95 else 1)" && ok "remix magnets keep >= 2 mm walls ($w mm)" || no "magnets" "wall $w"
"$CAD" remix.py "$R/thin_box.stl" thicken --min 2.0 --out "$R/thick_box.stl" >/dev/null 2>&1
"$CAD" preflight.py "$R/thick_box.stl" --json "$R/pf.json" >/dev/null 2>&1
n=$(python3 -c "import json;print(len(json.load(open('$R/pf.json'))['walls_under_1p2']))")
"$CAD" preflight.py "$R/thin_box.stl" --json "$R/pf0.json" >/dev/null 2>&1
n0=$(python3 -c "import json;print(len(json.load(open('$R/pf0.json'))['walls_under_1p2']))")
[ "$n" -lt "$n0" ] && ok "remix thicken: thin layers $n0 -> $n" || no "thicken" "$n0 -> $n thin layers"
for lid in slide press; do
  c=$("$CAD" make.py box 80 60 40 --lid $lid --label TEST 2>/dev/null | python3 -c "import json,sys;t=sys.stdin.read();print(json.loads(t[t.find('{'):])['check']['ok'])")
  [ "$c" = "True" ] && ok "make box ($lid lid): fits, $( [ $lid = slide ] && echo 'slides out clear + lift jams' || echo 'snug lip')" || no "make box $lid" "$c"
done
"$CAD" make.py keychain "TEST" > /dev/null 2>&1
k=$("$CAD" plate.py "$F/out/make/keychain_TEST/keychain.stl" --fill --name kc_test 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin)['items'])")
[ "${k:-0}" -ge 20 ] && ok "plate --fill packs $k keychains on one bed" || no "plate" "$k items"

echo; echo "max-model suite: $pass passed, $fail failed"; [ $fail -eq 0 ]
