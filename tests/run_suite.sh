#!/usr/bin/env bash
# Mold3D regression suite (pure python/CAD stack, no Blender, no model weights). Every check has a KNOWN right answer.
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

# 3b auto-support traps: a flat underside 0.3 mm over ANOTHER body fires; the same on one body / a 45 deg underside / a far gap does not;
#    cyclo11's real carrier-over-disc gap (0.30 mm) fires and its verdict says SUPPORTS: OFF (required)
"$CAD" - <<'PY' && ok "support_traps: flat 0.3 mm bridge over another body fires, single body / 45 deg V / 5 mm gap do not" || no "support_traps" "known answers differ"
import sys; sys.path.insert(0, '.'); import trimesh, numpy as np, preflight
def slab(): b = trimesh.creation.box([40, 40, 10]); b.apply_translation([0, 0, 5]); return b
def lid(z, w=20): b = trimesh.creation.box([w, w, 4]); b.apply_translation([0, 0, z + 2]); return b
two = trimesh.util.concatenate([slab(), lid(10.3)])
tr = preflight.support_traps(two)
assert len(tr) == 1 and abs(tr[0]["gap_min_mm"] - 0.3) < 0.05 and abs(tr[0]["area_mm2"] - 400) < 25, tr
assert preflight.support_traps(trimesh.util.concatenate([slab(), lid(15)])) == []                 # 5 mm gap: supports would not weld it
assert preflight.support_traps(slab()) == []                                                      # one body
d = trimesh.creation.box([14.14, 20, 14.14]); d.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 4, [0, 1, 0]))
d.apply_translation([0, 0, 10.3 + 10])                                                            # diamond: V underside at 45 deg, tip 0.3 over the slab
assert preflight.support_traps(trimesh.util.concatenate([slab(), d])) == [], "45 deg underside must not trap"
assert preflight.support_traps(two, angle=0.0) == [], "angle 0 = threshold off"
PY
"$CAD" preflight.py "$F/examples/cyclo11/cyclo11.stl" --json "$T/cy_pf.json" > "$T/cy_pf.txt" 2>&1
grep -q "SUPPORTS: OFF (required)" "$T/cy_pf.txt" && "$CAD" -c "import json,sys;r=json.load(open('$T/cy_pf.json'));t=r['support_traps'];sys.exit(0 if t and t[0]['gap_min_mm']<0.35 and sum(x['area_mm2'] for x in t)>500 and r['supports']=='off' else 1)" \
  && ok "preflight cyclo11: support_traps fire (0.30 mm gaps), SUPPORTS: OFF (required)" || no "cyclo11 traps" "see $T/cy_pf.txt"
"$CAD" preflight.py "$T/bridge10.stl" --json "$T/br_pf.json" > /dev/null 2>&1
"$CAD" -c "import json,sys;r=json.load(open('$T/br_pf.json'));sys.exit(0 if r['support_traps']==[] and 'required' not in r['supports_text'] else 1)" && ok "preflight single-body part: no support traps" || no "single body" "traps fired"

# 3c forge export: 3MF is valid, carries the supports decision (Orca JSON + Prusa lines), default name has the suffix, auto follows preflight
"$CAD" export3mf.py "$F/examples/cyclo11/cyclo11.stl" --out "$T/cy_auto.3mf" --no-orca > "$T/exp.log" 2>&1; rc=$?
"$CAD" export3mf.py "$T/bridge30.stl" --no-orca > "$T/exp2.log" 2>&1; rc2=$?
"$CAD" export3mf.py "$T/bridge10.stl" --supports on --out "$T/b10_on.3mf" --no-orca > /dev/null 2>&1
"$CAD" - "$T" $rc $rc2 <<'PY' && ok "export: cyclo11 auto -> supports OFF 3MF (orca 0 / prusa 0), bridge30 auto -> *_SUPPORTS-ON.3mf, --supports on honoured" || no "export" "see $T/exp.log"
import sys, zipfile, json, os, trimesh; sys.path.insert(0, '.'); import export3mf
T, rc, rc2 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); assert rc == 0 and rc2 == 0
tris, ext, ce, pm = export3mf.check_3mf(T + '/cy_auto.3mf'); assert ce == '0' and pm == '0' and tris > 1000 and abs(ext[0] - 86) < 0.5 and abs(ext[2] - 24) < 0.5, (tris, ext, ce, pm)
z = zipfile.ZipFile(T + '/cy_auto.3mf'); names = z.namelist()
assert {'[Content_Types].xml', '_rels/.rels', '3D/3dmodel.model', 'Metadata/project_settings.config', 'Metadata/Slic3r_PE.config'} <= set(names), names
assert json.loads(z.read('Metadata/project_settings.config')) == {'enable_support': '0', 'support_type': 'normal(auto)'}   # ONLY the supports checkbox
assert '; support_material_auto = 0' in z.read('Metadata/Slic3r_PE.config').decode()
assert os.path.exists(T + '/bridge30_SUPPORTS-ON.3mf') and export3mf.check_3mf(T + '/bridge30_SUPPORTS-ON.3mf')[2] == '1'
assert export3mf.check_3mf(T + '/b10_on.3mf')[2:] == ('1', '1')
PY

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

# 7 forge report: plain STL -> report.json with verdict + supports + files; bridge30 needs supports (3MF ON); fitcard-style mech.json folder adds moving parts
mkdir -p "$T/rep"; cp "$T/bridge30.stl" "$T/rep/bridge30.stl"
"$CAD" report.py "$T/rep/bridge30.stl" --no-preview --json > "$T/rep.log" 2>&1
"$CAD" - "$T/rep" <<'PY' && ok "report: bridge30 -> GO+SUPPORTS, supports on, ON-3MF, plain-English watch-for, no invented print/moving rows" || no "report" "see $T/rep.log"
import json, os, sys
d = json.load(open(sys.argv[1] + '/report.json'))
assert d['preflight']['verdict'] == 'GO+SUPPORTS' and d['preflight']['supports'] == 'on', d['preflight']
assert d['files']['3mf'].endswith('bridge30_SUPPORTS-ON.3mf') and os.path.exists(d['files']['3mf'])
assert 'moving_parts' not in d and 'slice' not in d and d['watch_for'], d
PY

# 8 first-five-minutes: the forge CLI from a DIFFERENT folder (relative paths, default output dir, help, doctor cache, Assumed row)
FG="$F/bin/forge"; W="$T/cwd"; rm -rf "$W"; mkdir -p "$W"; cp "$T/bridge30.stl" "$W/part.stl"
v=$(cd "$W" && "$FG" preflight part.stl 2>&1 | head -1)
case "$v" in "[GO+SUPPORTS] part.stl"*) ok "forge preflight with a RELATIVE path from another folder -> GO+SUPPORTS";; *) no "relative preflight" "got: $v";; esac
(cd "$W" && "$FG" export part.stl --out relout.3mf >/dev/null 2>&1; "$FG" split part.stl --out relsplit >/dev/null 2>&1)
[ -f "$W/relout.3mf" ] && [ -d "$W/relsplit" ] && ok "relative --out paths land in the caller's folder (export, split)" || no "relative --out" "$(ls "$W")"
e=$(cd "$W" && "$FG" preflight nothere.stl 2>&1); echo "$e" | grep -q "file not found" && ! echo "$e" | grep -q Traceback && ok "missing file -> one plain line, no traceback" || no "missing file" "$e"
e=$(cd "$W" && "$FG" preflgiht part.stl 2>&1); echo "$e" | grep -q "Did you mean 'preflight'" && ok "typo'd command -> 'Did you mean preflight'" || no "typo" "$e"
n=$("$FG" --help | grep -cE '^  [a-z0-9-]+ +[^ ]'); [ "$n" -ge 24 ] && ok "forge --help lists $n commands" || no "forge --help" "$n commands"
rm -rf "$W/mold3d"; (cd "$W" && env -u MOLD3D_OUT -u FORGE_OUT "$FG" sculpt >/dev/null 2>&1; env -u MOLD3D_OUT -u FORGE_OUT "$FG" make keychain HI >/dev/null 2>&1)
[ -f "$W/mold3d/make/keychain_HI/keychain.stl" ] && ok "default output is ./mold3d/<name>/ in the caller's folder" || no "default out dir" "$(find "$W" -maxdepth 3 | head)"
mkdir -p "$W/elsewhere"; (cd "$W" && MOLD3D_OUT="$W/elsewhere" "$FG" make keychain HI >/dev/null 2>&1)
[ -f "$W/elsewhere/make/keychain_HI/keychain.stl" ] && ok "MOLD3D_OUT overrides the output folder" || no "MOLD3D_OUT" "$(ls "$W/elsewhere")"
export MOLD3D_CACHE="$T/doctor_cache"; rm -rf "$MOLD3D_CACHE"
"$FG" doctor --fresh >/dev/null 2>&1; s=$(python3 -c "import time;print(time.time())"); "$FG" doctor > "$T/doctor2.log" 2>&1
dt=$(python3 -c "import time;print(round(time.time()-$s,2))")
grep -q "cached result" "$T/doctor2.log" && python3 -c "import sys;sys.exit(0 if $dt < 3 else 1)" && ok "forge doctor: second run is a cache hit (${dt}s)" || no "doctor cache" "${dt}s, $(tail -2 "$T/doctor2.log")"
unset MOLD3D_CACHE
mkdir -p "$T/asm"; cp "$T/bridge30.stl" "$T/asm/bridge30.stl"
echo '{"assumed": {"screw size": "M4", "phone width": "72 mm"}}' > "$T/asm/spec.json"
"$CAD" report.py "$T/asm/bridge30.stl" --no-preview --no-export > "$T/asm.log" 2>&1
grep -q "^| Assumed | screw size M4; phone width 72 mm" "$T/asm.log" && ok "report: spec.json 'assumed' -> an Assumed row" || no "report Assumed row" "$(cat "$T/asm.log")"
grep -q "^| Assumed" "$T/rep.log" && no "report: no assumed values -> no Assumed row" "row shown" || ok "report: nothing assumed -> no Assumed row"

# 9 the "no guessed numbers" gate: fit numbers in spec.json carry a source; ASSUMED (or a made-up source) on a fit number
#   stamps the report NOT FIT-CHECKED with the cheapest fix; all sourced -> "fit-checked"; verify shows it as a WARN, never a FAIL
G="$T/fitgate"; rm -rf "$G"; mkdir -p "$G"; cp "$T/bridge10.stl" "$G/bridge10.stl"
echo '{"fit": {"pod diameter": {"mm": 38.2, "source": "measured"}, "tube diameter": {"mm": 25, "source": "ASSUMED"}, "M3 screw": {"mm": 3.4, "source": "guess"}}}' > "$G/spec.json"
"$CAD" report.py "$G/bridge10.stl" --no-preview --no-export > "$G/rep.log" 2>&1
grep -q "PRINT REPORT.*NOT FIT-CHECKED" "$G/rep.log" && grep -q "^| Fit | ⚠️ NOT FIT-CHECKED: tube diameter 25 mm and M3 screw 3.4 mm were assumed.*Cheapest fix: ask one question: what is the tube diameter? (default 25 mm)" "$G/rep.log" \
  && grep -q "^| Assumed | tube diameter 25 mm; M3 screw 3.4 mm" "$G/rep.log" && ok "fit gate: ASSUMED + made-up source -> header stamped NOT FIT-CHECKED, Fit row names both + cheapest fix" || no "fit gate stamp" "$(head -5 "$G/rep.log")"
"$CAD" verify_cli.py "$G/bridge10.stl" --spec "$G/spec.json" --json > "$G/verify.json" 2>/dev/null; rc=$?
"$CAD" -c "import json,sys;r=json.load(open('$G/verify.json'));f=[c for c in r['checks'] if c['name']=='fit_sources'][0];sys.exit(0 if f['status']=='WARN' and f['value']==2 and r['status']!='FAIL' and $rc==0 else 1)" && ok "fit gate: verify -> WARN fit_sources (2 assumed), exit 0 (a warning, not a failure)" || no "fit gate verify" "$(cat "$G/verify.json" | tail -5)"
echo '{"fit": {"pod diameter": {"mm": 38.2, "source": "measured"}, "M3 screw": {"mm": 3.4, "source": "parts-find"}}}' > "$G/spec.json"
"$CAD" report.py "$G/bridge10.stl" --no-preview --no-export > "$G/rep2.log" 2>&1
! grep -q "NOT FIT-CHECKED" "$G/rep2.log" && grep -q "^| Fit | ✅ fit-checked: 2 fit numbers sourced (1 measured, 1 parts-find)" "$G/rep2.log" && ! grep -q "^| Assumed" "$G/rep2.log" && ok "fit gate: every fit number sourced -> no stamp, 'fit-checked: 2 fit numbers sourced'" || no "fit gate clean" "$(head -5 "$G/rep2.log")"
echo '{"fit": {"screw size": {"mm": 4, "source": "ASSUMED"}}}' > "$G/spec.json"
"$CAD" report.py "$G/bridge10.stl" --no-preview --no-export 2>/dev/null | grep -q 'Cheapest fix: `forge parts-find "screw size"`' && ok "fit gate: a screw's cheapest fix is forge parts-find" || no "fit gate fix" "wrong fix"

# 10 spec-as-test: named checks with KNOWN answers on a generated block (40x40x10, a 6.0 mm through-hole at (10,10), a corner notch)
N="$T/named"; rm -rf "$N"; mkdir -p "$N"
"$CAD" - "$N" <<'PY'
import sys; sys.path.insert(0, '.'); import meshkit as mk
from manifold3d import Manifold
o = sys.argv[1] + '/'
mk.save(mk.box(-20,-20,0,20,20,10) - Manifold.cylinder(10.2, 3.0, 3.0, 96).translate([10,10,-0.1]) - mk.box(-20,-20,4,-10,-5,11), o + 'block.stl')
mk.save(Manifold.cylinder(12, 2.7, 2.7, 96).translate([10,10,-1]), o + 'pin54.stl')      # 5.4 mm pin in a 6.0 hole = 0.30 per side
mk.save(Manifold.cylinder(12, 2.95, 2.95, 96).translate([10,10,-1]), o + 'pin59.stl')    # 5.9 mm pin = 0.05 per side
PY
cat > "$N/spec.json" <<'SPEC'
{"bbox_mm": [40,40,10], "components": 1, "min_wall_mm": 2.0,
 "checks": {
  "hole for the M6 pin": {"hole": {"at": [10,10], "d": 6.0, "tol": 0.2}},
  "hole is really 8 mm (wrong on purpose)": {"hole": {"at": [10,10], "d": 8.0}},
  "hole where there is only solid": {"hole": {"at": [-10,10], "d": 6.0}},
  "corner notch is open": {"empty_at": [-15, -12, 7]},
  "corner notch is closed (wrong on purpose)": {"solid_at": [-15, -12, 7]},
  "floor is solid under the notch": {"solid_at": [-15, -12, 2]},
  "the 5.4 pin fits with 0.3": {"fits": "pin54.stl", "clearance": 0.3},
  "the 5.9 pin fits with 0.3 (wrong on purpose)": {"fits": "pin59.stl", "clearance": 0.3},
  "10 mm tall": {"height_mm": [9.9, 10.1]},
  "made-up check type": {"roundness": 3}
 }}
SPEC
"$CAD" verify_cli.py "$N/block.stl" --spec "$N/spec.json" > "$N/plain.txt" 2>&1; rc=$?
"$CAD" verify_cli.py "$N/block.stl" --spec "$N/spec.json" --json > "$N/verify.json" 2>/dev/null
"$CAD" - "$N" $rc <<'PY' && ok "spec-as-test: 15 of 20 green, every named check gives the known answer (hole 6.00, solid, notch, fits 0.30 vs 0.05, unknown type = FAIL), exit 1" || no "spec-as-test" "see $N/plain.txt"
import json, sys
N, rc = sys.argv[1], int(sys.argv[2]); r = json.load(open(N + '/verify.json')); c = {x['name']: x for x in r['checks']}
assert rc == 1 and r['status'] == 'FAIL' and (r['summary']['green'], r['summary']['total']) == (15, 20), (rc, r['summary'])
assert c['hole for the M6 pin']['status'] == 'PASS' and abs(c['hole for the M6 pin']['value'] - 6.0) < 0.05
assert c['hole is really 8 mm (wrong on purpose)']['status'] == 'FAIL' and 'measured 6.0' in c['hole is really 8 mm (wrong on purpose)']['plain']
assert c['hole where there is only solid']['status'] == 'FAIL' and 'solid there' in c['hole where there is only solid']['plain']
assert c['corner notch is open']['status'] == 'PASS' and c['corner notch is closed (wrong on purpose)']['status'] == 'FAIL' and c['floor is solid under the notch']['status'] == 'PASS'
assert c['the 5.4 pin fits with 0.3']['status'] == 'PASS' and abs(c['the 5.4 pin fits with 0.3']['value'] - 0.30) < 0.03
assert c['the 5.9 pin fits with 0.3 (wrong on purpose)']['status'] == 'FAIL' and 'too tight' in c['the 5.9 pin fits with 0.3 (wrong on purpose)']['plain']
assert c['10 mm tall']['status'] == 'PASS' and c['made-up check type']['status'] == 'FAIL' and 'unknown check type' in c['made-up check type']['plain']
assert all(x.get('plain') for x in r['checks']), 'every row has a plain sentence'
first = open(N + '/plain.txt').readline()
assert first.startswith('CHECKS for block.stl: 15 of 20 green'), first
PY
(cd "$W" && cp "$N/block.stl" . && cp "$N/spec.json" . && cp "$N"/pin5*.stl . && "$FG" verify block.stl --spec spec.json > verify_rel.txt 2>&1); head -1 "$W/verify_rel.txt" | grep -q "15 of 20 green" && ok "forge verify with RELATIVE stl + spec from another folder (fits dummies resolve next to the spec)" || no "forge verify relative" "$(head -3 "$W/verify_rel.txt")"
"$CAD" report.py "$N/block.stl" --no-preview --no-export > "$N/rep.log" 2>&1; rc=$?
grep -q "^| Checks | ❌ 15 of 20 green: hole is really 8 mm (wrong on purpose): measured 6.00 mm at (10, 10), wanted 8 ±0.2; hole where there is only solid: no hole at (-10, 10): the part is solid there; and 3 more" "$N/rep.log" && [ $rc = 4 ] && ok "report: Checks row names the red lines in plain words, exit 4 (not done)" || no "report Checks row" "rc=$rc $(grep Checks "$N/rep.log")"
echo '{"bbox_mm": [40,40,10], "components": 1, "min_wall_mm": 2.0}' > "$N/spec.json"
"$CAD" report.py "$N/block.stl" --no-preview --no-export --fresh > "$N/rep2.log" 2>&1; rc=$?
grep -q "^| Checks | ✅ 10 of 10 green |" "$N/rep2.log" && [ $rc = 0 ] && ok "report: the 3-line fast-lane spec -> 'Checks: 10 of 10 green', exit 0" || no "report fast lane" "rc=$rc $(grep Checks "$N/rep2.log")"

# 11 per-printer thresholds: preflight judges against the profile, not constants. Same STL, different profile, different verdict.
P="$T/printers"; rm -rf "$P"; mkdir -p "$P"
echo '{"name": "long-bridge test", "bridge_mm": 40, "sources": {"bridge_mm": "test fixture"}}' > "$P/br40.json"
echo '{"name": "short-bridge test", "bridge_mm": 5, "overhang_area_mm2": 50, "sources": {"bridge_mm": "test fixture"}}' > "$P/br5.json"
v1=$(FORGE_PRINTER="$P/br40.json" "$CAD" preflight.py "$T/bridge30.stl" 2>/dev/null | head -1 | sed 's/^\[\([^]]*\)\].*/\1/')
v2=$(FORGE_PRINTER="$P/br5.json" "$CAD" preflight.py "$T/bridge10.stl" 2>/dev/null | head -1 | sed 's/^\[\([^]]*\)\].*/\1/')
[ "$v1" = "GO" ] && [ "$v2" = "GO+SUPPORTS" ] && ok "preflight reads bridge_mm / overhang_area_mm2 from the printer profile (30 mm bridge: GO at 40; 10 mm bridge: GO+SUPPORTS at 5 mm / 50 mm2)" || no "profile bridge_mm" "bridge30@40=$v1 bridge10@5=$v2"
"$CAD" - "$T" <<'PY'
import sys; sys.path.insert(0, '.'); import meshkit as mk
mk.save(mk.box(0, 0, 0, 250, 20, 10), sys.argv[1] + '/bar250.stl')
PY
v1=$("$CAD" preflight.py "$T/bar250.stl" 2>/dev/null | head -1 | sed 's/^\[\([^]]*\)\].*/\1/')
v2=$(FORGE_PRINTER="$F/knowledge/printers/anycubic-kobra-x.json" "$CAD" preflight.py "$T/bar250.stl" --json "$P/kobra.json" 2>/dev/null | head -1 | sed 's/^\[\([^]]*\)\].*/\1/')
[ "$v1" = "NO-GO" ] && [ "$v2" = "GO" ] && "$CAD" -c "import json,sys;r=json.load(open('$P/kobra.json'));sys.exit(0 if r['limits']['bed']==[260,260,260] and r['printer']=='Anycubic Kobra X' else 1)" \
  && ok "a 250 mm bar: NO-GO on the generic 220 bed, GO on the Anycubic Kobra X (260 cube); preflight.json records the limits + printer" || no "kobra x bed" "generic=$v1 kobra=$v2"
"$CAD" - <<'PY' && ok "every profile in knowledge/printers has a source line for the bed and all 7 thresholds; forge printer prints them" || no "profile sources" "a profile lacks a source"
import glob, json, os, sys; sys.path.insert(0, '.'); import printer
for f in glob.glob(os.path.join(printer.PROFILES_DIR, '*.json')):
    d = json.load(open(f)); src = d.get('sources', {})
    for k in ('bed',) + printer.THRESHOLDS:
        assert k in d and k in src and len(src[k]) > 20, (os.path.basename(f), k)
assert len(glob.glob(os.path.join(printer.PROFILES_DIR, '*.json'))) >= 4
PY
out=$(FORGE_PRINTER="$P/active.json" "$CAD" printer.py use anycubic-kobra-x 2>&1); FORGE_PRINTER="$P/active.json" "$CAD" printer.py > "$P/show.txt" 2>&1
echo "$out" | grep -q "now using Anycubic Kobra X" && grep -q "bed 260 x 260 x 260" "$P/show.txt" && grep -c "UNVERIFIED\|http\|PrintConfig\|house value" "$P/show.txt" | python3 -c "import sys;sys.exit(0 if int(sys.stdin.read())>=6 else 1)" \
  && ok "forge printer use anycubic-kobra-x -> active profile; forge printer shows every threshold with its source" || no "forge printer" "$out $(cat "$P/show.txt")"
echo '{"name": "edited by hand", "bridge_mm": 25}' > "$P/noscr.json"
FORGE_PRINTER="$P/noscr.json" "$CAD" printer.py | grep -q "bridge_mm  *25 mm  *UNVERIFIED: set in this profile without a source line" && ok "a threshold edited without a source line shows as UNVERIFIED, never credited to the generic source" || no "unverified edit" "$(FORGE_PRINTER="$P/noscr.json" "$CAD" printer.py | grep bridge)"

# gap_min: a slider in a channel. Flush faces are their own FAIL ("touch"), never a pass; a tagged stop is allowed;
#   a 0.10 mm side is too tight; sliding into the end wall collides; 0.25 all round passes along the whole path.
#   contents: a 2-colour export reads back 2 pieces / 2 filaments; text on the bed face is flagged as not visible from the top.
"$CAD" - "$T" <<'PY2' && ok "gap_min: 0.25 all round PASS, flush floor FAIL as touching, tagged stop PASS, 0.10 side FAIL, end-wall collision FAIL; contents flags bed-face text" || no "gap_min / contents" "known answers differ"
import sys, os, json, subprocess, trimesh, numpy as np; sys.path.insert(0, '.'); import verify_lib as V
T = sys.argv[1]
def box(lo, hi): return trimesh.creation.box(extents=np.subtract(hi, lo), transform=trimesh.transformations.translation_matrix(np.add(lo, hi) / 2))
def save(m, n): p = os.path.join(T, n); m.export(p); return p
chan = save(trimesh.util.concatenate([box([-20, -6, -2], [20, 6, 0]), box([-20, -6, 0], [20, -5.25, 4]), box([-20, 5.25, 0], [20, 6, 4]), box([20, -6, -2], [21, 6, 4])]), "chan.stl")
good = save(box([-10, -5, 0.25], [10, 5, 3]), "slider_ok.stl")
flush = save(box([-10, -5, 0.0], [10, 5, 3]), "slider_flush.stl")
tight = save(box([-10, -5.15, 0.25], [10, 5, 3]), "slider_tight.stl")
def chk(m, **g): return V.check_gap_min(m, {"gap_min": {"between": m, "and": chan, "min_mm": 0.25, **g}}, T)
r = chk(good, path=[[0, 0, 0], [9, 0, 0]], steps=3); assert r[0] == "PASS", r
r = chk(flush); assert r[0] == "FAIL" and "touch" in r[2], r
r = chk(flush, stops=[[[-21, -5.5, -0.1], [21, 5.5, 0.1]]]); assert r[0] == "PASS", r
r = chk(tight); assert r[0] == "FAIL" and "gap 0.10" in r[2], r
r = chk(good, path=[[0, 0, 0], [12, 0, 0]], steps=4); assert r[0] == "FAIL" and "collide" in r[2], r
body = save(box([-15, -8, 0], [15, 8, 4]), "plate_body.stl")
txt_bed = save(box([-8, -3, 0], [8, 3, 0.6]), "plate_text.stl")
out = os.path.join(T, "plate_set.3mf")
p = subprocess.run([sys.executable, "export3mf.py", "--piece", f"plate={body}@1,{txt_bed}@2", "--piece", f"stand={good}@1", "--supports", "off", "--no-orca",
                    "--out", out, "--expect", json.dumps({"pieces": 2, "filaments": 2, "supports": "off", "visible_from_top": ["text"]})], capture_output=True, text=True)
assert p.returncode == 1 and "only on the bed face" in p.stdout and "2 piece(s), filament slot(s) 1, 2" in p.stdout, p.stdout + p.stderr
txt_top = save(box([-8, -3, 3.4], [8, 3, 4.0]), "plate_text_top.stl")
p = subprocess.run([sys.executable, "export3mf.py", "--piece", f"plate={body}@1,{txt_top}@2", "--supports", "off", "--no-orca", "--out", out,
                    "--expect", json.dumps({"pieces": 1, "filaments": 2, "visible_from_top": ["text"]})], capture_output=True, text=True)
assert p.returncode == 0 and "MATCHES THE ASK" in p.stdout, p.stdout + p.stderr
PY2

echo; echo "Mold3D suite: $pass passed, $fail failed"; [ $fail -eq 0 ]
