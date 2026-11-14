#!/usr/bin/env python3
"""forge <run|doctor|preflight|export|report|...> ...   (see bin/forge --help)
run <part_file> [--lane b123d|scad|bpy] [--spec spec.json] [--name N] [--no-render] [--section z=5] [--ref img] [--eevee]
  -> out/<name>/{<name>.stl, views/, sheet.png, verify.json, REPORT.md, src.*, iter_NN/}. Exit 1 on FAIL."""
import argparse, json, os, shutil, subprocess, sys, shlex
HERE = os.path.dirname(os.path.abspath(__file__))
FORGE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import forge_env
import verify_lib as V

CAD_PY = forge_env.CAD_PY
OPENSCAD = forge_env.find_openscad() or "openscad"

HINTS = {
    "watertight": "Mesh has holes. bpy: union operands with solver EXACT / fix text via forge_bpy.text(); b123d: check Solid is valid (part.is_valid); scad: remove coplanar faces (add 0.01 overlap in unions/differences).",
    "winding": "Flipped faces: recalc normals (bpy: bmesh recalc_face_normals) or rebuild the offending boolean.",
    "normals_outward": "Mesh is inside-out: flip normals / check the boolean operand order.",
    "non_empty": "Part has ~no volume: a boolean deleted it. Print volumes before/after each boolean; operands must share one coordinate frame.",
    "components": "Disconnected bodies. Overlap unions by ~0.01-0.1 mm so they fuse, or set spec components to the intended count (multi-part plates).",
    "bed_fit": "Too big for the bed: scale, split into parts with alignment keys, or rotate to fit.",
    "supports": "Reduce overhangs: re-orient, add chamfers (<=45 deg) instead of flat ceilings, or split the part so flat faces sit on the bed.",
    "min_wall": "Thicken the listed regions (>=1.2 mm for 0.4 nozzle; 2 mm for strength) at the cluster locations.",
    "spec_bbox": "Dimensions differ from spec: check units (1 unit = 1 mm), scale and which axis is which.",
    "spec_volume": "Volume outside expected range: a boolean probably dropped/duplicated geometry.",
    "render": "Previews are off (Blender didn't start). Everything else works. If Blender is installed and crashed (exit 139) inside a sandbox, re-run outside it.",
    "bed_contact": "Little surface on the bed: add a flat base/brim or flip the part so its biggest flat face is z-min.",
}


def lane_of(path, forced):
    if forced: return forced
    ext = os.path.splitext(path)[1].lower()
    if ext == ".scad": return "scad"
    if ext == ".py":
        txt = open(path).read()
        if "import bpy" in txt or "from bpy" in txt or "forge_bpy" in txt: return "bpy"
        if "build123d" in txt: return "b123d"
    sys.exit(f"forge: cannot infer lane for {path}; pass --lane b123d|scad|bpy")


def run_lane(lane, part, out_stl, parts_dir, log):
    env = dict(os.environ, FORGE_OUT_STL=out_stl, FORGE_PARTS_DIR=parts_dir, FORGE_LIB=os.path.join(FORGE, "lib"))
    env["PYTHONPATH"] = os.path.join(FORGE, "lib") + os.pathsep + env.get("PYTHONPATH", "")
    if lane == "scad" and not forge_env.find_openscad():
        sys.exit("forge: the OpenSCAD lane is off (OpenSCAD isn't installed). Everything else works. Install OpenSCAD or set OPENSCAD=/path, or use the b123d lane.")
    if lane == "b123d": cmd = [CAD_PY, part]
    elif lane == "scad": cmd = [OPENSCAD, "--backend=Manifold", "-o", out_stl, part]
    else: cmd = [os.path.join(FORGE, "bin", "blender_py"), part]
    print("forge: lane", lane, "->", " ".join(shlex.quote(c) for c in cmd))
    p = subprocess.run(cmd, env=env, cwd=os.path.dirname(os.path.abspath(part)), capture_output=True, text=True, timeout=900)
    open(log, "w").write(f"$ {' '.join(cmd)}\nrc={p.returncode}\n--- stdout\n{p.stdout}\n--- stderr\n{p.stderr}")
    if p.returncode != 0:
        tail = (p.stdout + p.stderr)[-1500:]
        hint = "\nHINT: Blender crashes at startup inside some agent sandboxes (no GPU access); re-run outside the sandbox." if p.returncode in (139, -11, -6, 134) or "sandbox" in tail.lower() else ""
        sys.exit(f"forge: part script FAILED (rc={p.returncode}). Log {log}\n{tail}{hint}")
    if not os.path.exists(out_stl) or os.path.getsize(out_stl) == 0:
        sys.exit(f"forge: part script exited 0 but wrote no STL at $FORGE_OUT_STL ({out_stl}). Export to os.environ['FORGE_OUT_STL'].")


def next_iter(d):
    n = [int(x[5:]) for x in os.listdir(d) if x.startswith("iter_") and x[5:].isdigit()] if os.path.isdir(d) else []
    return (max(n) + 1) if n else 1


def cmd_run(a):
    part = os.path.abspath(a.part)
    if not os.path.exists(part): sys.exit(f"forge: no such part file {part}")
    lane = lane_of(part, a.lane)
    name = a.name or os.path.splitext(os.path.basename(part))[0]
    od = os.path.join(FORGE, "out", name); os.makedirs(od, exist_ok=True)
    for stale in ("views", "parts"): shutil.rmtree(os.path.join(od, stale), ignore_errors=True)
    for f in ("sheet.png", "verify.json", "REPORT.md"):
        if os.path.exists(os.path.join(od, f)): os.remove(os.path.join(od, f))
    stl = os.path.join(od, name + ".stl"); parts = os.path.join(od, "parts")
    if os.path.exists(stl): os.remove(stl)
    os.makedirs(parts, exist_ok=True)
    spec = json.load(open(a.spec)) if a.spec else {}
    run_lane(lane, part, stl, parts, os.path.join(od, "build.log"))
    try:
        sys.argv = ["clean", stl]
        import clean_stl; clean_stl.clean(stl)
    except Exception as e:
        print("forge: clean step failed (continuing, verify will tell):", e)
    res = V.verify(stl, spec)
    rows = res["checks"]
    # --- render
    render_ok = True
    if not a.no_render:
        summ = os.path.join(od, "_summary.txt")
        open(summ, "w").write("\n".join([f"{name}  [{res['status']}]  lane={lane}"] + [f"[{r['status']:4}] {r['name']}: {str(r['value'])[:30]}" for r in rows]))
        rc = [os.path.join(FORGE, "bin", "render"), stl, od, "--summary", summ]
        if a.section: rc += ["--section", a.section]
        if a.ref: rc += ["--ref", a.ref]
        if a.eevee: rc += ["--eevee"]
        p = subprocess.run(rc, capture_output=True, text=True)
        open(os.path.join(od, "render.log"), "w").write(p.stdout + p.stderr)
        os.remove(summ)
        render_ok = p.returncode == 0 and os.path.exists(os.path.join(od, "sheet.png"))
        if not render_ok:
            rows.append(V.row("render", "FAIL", None, "previews are off (Blender isn't installed or didn't start). Everything else works. See out/%s/render.log; exit 139 = Blender crashed (re-run outside an agent sandbox)" % name))
            print(p.stdout[-800:], p.stderr[-800:])
    res["status"] = "FAIL" if any(r["status"] == "FAIL" for r in rows) else ("WARN" if any(r["status"] == "WARN" for r in rows) else "PASS")
    res["lane"] = lane; res["name"] = name
    json.dump(res, open(os.path.join(od, "verify.json"), "w"), indent=1, default=str)
    # --- report
    L = [f"# forge report: {name}", "", f"**{res['status']}** | lane `{lane}` | bbox {res['info']['bbox_mm']} mm | vol {res['info']['volume_mm3']} mm3 | ~{res['info']['mass_g_pla']} g PLA", "",
         "| check | status | value | detail |", "|---|---|---|---|"]
    for r in rows: L.append(f"| {r['name']} | {r['status']} | {r['value']} | {r['detail']} |")
    L += ["", "## Next step"]
    bad = [r for r in rows if r["status"] in ("FAIL", "WARN")]
    if not bad:
        L.append("All numeric checks pass. Now LOOK at `sheet.png` (Read it): does it match the intent (shape, hole positions, text legible, orientation)? Numbers catch print-ruining defects, renders catch coarse ones.")
    for r in bad:
        L.append(f"- **{r['status']} {r['name']}**: {HINTS.get(r['name'], r['detail'])}")
    if res["status"] != "FAIL":
        L.append("- Still view `sheet.png` / `views/*.png` before declaring done; use `--section z=<mm>` to inspect cavities.")
    L += ["", f"Files: `{stl}`, `{od}/sheet.png`, `{od}/views/`, `{od}/build.log`. Re-run: `forge/bin/forge run {part}" + (f" --spec {a.spec}" if a.spec else "") + f" --name {name}`"]
    open(os.path.join(od, "REPORT.md"), "w").write("\n".join(L) + "\n")
    # --- source + history
    shutil.copy(part, os.path.join(od, "src" + os.path.splitext(part)[1]))
    n = next_iter(od); it = os.path.join(od, f"iter_{n:02d}"); os.makedirs(it)
    for f in os.listdir(od):
        if f.startswith("iter_"): continue
        s = os.path.join(od, f); d = os.path.join(it, f)
        shutil.copytree(s, d) if os.path.isdir(s) else shutil.copy2(s, d)
    print("\n".join(L))
    print(f"\nforge: {res['status']}  (iteration {n}, saved {it})")
    sys.exit(1 if res["status"] == "FAIL" else 0)


def cmd_doctor(a):
    ok = True
    def chk(label, good, fix="", required=True, off=None):
        nonlocal ok
        if off and not good and not required:
            print(f"  [optional] {off}\n        to turn it on: {fix}")
        else:
            print(f"  [{'ok' if good else ('MISSING' if required else 'optional')}] {label}" + ("" if good else f"\n        fix: {fix}"))
        if required: ok &= bool(good)
    import printer
    print("forge doctor")
    print(f"  [info] FORGE_ROOT={FORGE}")
    pr = printer.load()
    print(f"  [info] printer: {pr['name']}  bed {pr['bed']}  nozzle {pr['nozzle']}  (knowledge/printer.json)")
    bl = forge_env.find_blender()
    chk("Blender (renders, showcase, heatmaps)", bl, "install Blender 4.x/5.x (https://www.blender.org) or set BLENDER=/path/to/blender", required=False,
        off="Renders, previews and heatmaps are off (Blender isn't installed). Everything else works.")
    if bl:
        p = subprocess.run([bl, "-b", "--python-expr", "import bpy;print('BLV',bpy.app.version_string)"], capture_output=True, text=True)
        good = "BLV" in p.stdout
        chk("Blender runs headless" + (" (" + p.stdout.split("BLV")[1].split()[0] + ")" if good else f" (exit {p.returncode})"), good,
            "exit 139/-11 usually means an agent sandbox is hiding the GPU: run this command outside the sandbox" if p.returncode in (139, -11, -6, 134) else "run Blender manually once; check OS security prompts", required=False)
    chk("openscad (only for the scad lane)", forge_env.find_openscad(), "install OpenSCAD 2021+ (a Manifold-backend nightly is best) or set OPENSCAD=...", required=False,
        off="The OpenSCAD part lane is off (OpenSCAD isn't installed). Everything else works.")
    chk(f"CAD python: {CAD_PY}", os.path.exists(CAD_PY), "python3.12 -m venv .venv-cad && .venv-cad/bin/pip install -r requirements-cad.txt")
    if os.path.exists(CAD_PY):
        p = subprocess.run([CAD_PY, "-c", "import build123d,trimesh,numpy,scipy,PIL;print(build123d.__version__)"], capture_output=True, text=True)
        chk("build123d + trimesh + numpy + scipy + pillow importable " + p.stdout.strip(), p.returncode == 0, "pip install -r requirements-cad.txt")
        p = subprocess.run([CAD_PY, "-c", "import manifold3d,shapely,pxr,cv2,skimage,fast_simplification,lxml,networkx;print('ok')"], capture_output=True, text=True)
        chk("CAD stack (manifold3d, usd-core, opencv, scikit-image, lxml, networkx ...)", "ok" in p.stdout, "pip install -r requirements-cad.txt")
    ai = forge_env.AI_PY
    have_ai = os.path.exists(ai) and ai != CAD_PY
    chk(f"AI python (text3d / looks): {ai}", have_ai, "python3.12 -m venv .venv-ai && .venv-ai/bin/pip install -r requirements-ai.txt", required=False,
        off="Text-to-3D and Looks Score are off (the AI environment isn't installed). Everything else works.")
    hub = os.path.join(os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface"), "hub")
    for rid in ("models--SimianLuo--LCM_Dreamshaper_v7", "models--tencent--Hunyuan3D-2mini", "models--openai--clip-vit-base-patch32"):
        chk(f"model downloaded: {rid.split('--', 1)[1]}", os.path.isdir(os.path.join(hub, rid)), "downloaded on first `forge text3d` / `forge looks` run (see THIRD_PARTY_NOTICES.md for licenses)", required=False)
    hy = os.path.join(HERE, "text3d", "Hunyuan3D-2")
    chk("Hunyuan3D-2 source checkout (lib/text3d/Hunyuan3D-2)", os.path.isdir(hy), "git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2 lib/text3d/Hunyuan3D-2   (only for `forge text3d`)", required=False)
    chk("ffmpeg (showcase videos)", shutil.which("ffmpeg"), "install ffmpeg", required=False,
        off="Showcase videos are off (ffmpeg isn't installed). Everything else works.")
    chk("slicer hook (printer.json slicer_cmd / FORGE_SLICER_CMD)", bool(os.environ.get("FORGE_SLICER_CMD") or pr.get("slicer_cmd")),
        "set slicer_cmd in knowledge/printer.json (or FORGE_SLICER_CMD)", required=False,
        off="Print time and grams are off (no slicer hook set). Everything else works; slice the file in your slicer.")
    fj = os.path.join(FORGE, "knowledge", "fit.json")
    print("  [info] fit.json:", "calibrated" if os.path.exists(fj) else "NOT calibrated yet -> print the Fit Card (forge mech build fitcard)")
    print("\n" + ("all required dependencies present" if ok else "some required dependencies missing (see fixes above)"))
    print("note: Blender / OpenSCAD / GPU (MPS, CUDA) steps can crash inside agent sandboxes; run them outside one.")
    sys.exit(0 if ok else 1)


def cmd_topo(rest):
    """forge topo part.step [--face sN.fM | --near=x,y,z | --edges]: addressable faces/holes + plain-English features (lib/topo.py)."""
    sys.exit(subprocess.run([CAD_PY, os.path.join(HERE, "topo.py")] + rest).returncode)


def cmd_parts_find(rest):
    """forge parts-find "M3 socket head 12" [--download] [--limit N]: search the step.parts catalog (screws, bearings, motors, boards)."""
    sys.exit(subprocess.run([CAD_PY, os.path.join(HERE, "step_parts.py")] + rest).returncode)


def cmd_step2stl(rest):
    """forge step2stl in.step [out.stl]: convert a (downloaded) STEP into an STL dummy for `verify --assembly` / `--move-*` fit checks."""
    if not rest: sys.exit("usage: forge step2stl in.step [out.stl]")
    src = os.path.abspath(rest[0]); dst = os.path.abspath(rest[1]) if len(rest) > 1 else os.path.splitext(src)[0] + ".stl"
    code = ("import sys;from build123d import import_step,export_stl;s=import_step(sys.argv[1]);bb=s.bounding_box();"
            "export_stl(s,sys.argv[2],tolerance=0.01,angular_tolerance=0.1);print('wrote',sys.argv[2],'bbox mm',[round(v,2) for v in bb.size],'min',[round(v,2) for v in bb.min])")
    sys.exit(subprocess.run([CAD_PY, "-c", code, src, dst]).returncode)


def cmd_movecheck(rest):
    """forge movecheck model.stl|3mf [--json out]: bodies, per-joint min gap, fuse-risk area (<0.2 mm), overhang %. Same check for human + Max models."""
    sys.exit(subprocess.run([CAD_PY, os.path.join(HERE, "movecheck.py")] + rest).returncode)


def cmd_grade(rest):
    """forge grade attempt.stl truth.stl [--json out]: pose-free voxel IoU + chamfer/h95 mm vs a ground-truth mesh (e.g. step.parts STEP->STL)."""
    sys.exit(subprocess.run([CAD_PY, os.path.join(HERE, "grade.py")] + rest).returncode)


HG_PY = forge_env.AI_PY


def _cad(script, rest, cwd=None):
    sys.exit(subprocess.run([CAD_PY, os.path.join(HERE, script)] + rest, cwd=cwd or HERE).returncode)


def cmd_mech(rest):
    """forge mech list | build <name> [k=v..] | test [names]: MechKit verified print-in-place mechanisms."""
    sys.exit(subprocess.run([CAD_PY, "-m", "mechkit.cli"] + rest, cwd=HERE).returncode)


def cmd_heat(rest):
    """forge heat model.stl: preflight risk heatmap (red = needs support) rendered by Blender."""
    if not rest: sys.exit("usage: forge heat model.stl")
    stl = os.path.abspath(rest[0]); ply = os.path.splitext(stl)[0] + "_heat.ply"; png = os.path.splitext(stl)[0] + "_heat.png"
    subprocess.run([CAD_PY, os.path.join(HERE, "preflight.py"), stl, "--heat", ply])
    r = subprocess.run([os.path.join(FORGE, "bin", "blender_py"), os.path.join(HERE, "heat_render.py"), ply, png], capture_output=True)
    print("heat ->", png.replace(".png", "_iso.png"), png.replace(".png", "_under.png")); sys.exit(r.returncode)


NEW = {
    "mech": cmd_mech,
    "fit": lambda r: _cad("fit.py", r or ["show"]),
    "flexify": lambda r: _cad("flexify.py", r),
    "preflight": lambda r: _cad("preflight.py", r),
    "heat": cmd_heat,
    "report": lambda r: _cad("report.py", [os.path.abspath(r[0])] + r[1:] if r and not r[0].startswith("-") else r),
    "export": lambda r: _cad("export3mf.py", [os.path.abspath(x) if i == 0 or (i and r[i - 1] == "--out") else x for i, x in enumerate(r)]),
    "text3d": lambda r: sys.exit(subprocess.run([os.path.join(HERE, "text3d", "text3d.sh")] + r).returncode),
    "ar": lambda r: _cad("ar.py", r),
    "showcase": lambda r: _cad("showcase.py", ([os.path.abspath(r[0])] + r[1:]) if r else r),
    "gridfinity": lambda r: _cad("gridfinity.py", r),
    "photofit": lambda r: _cad("photofit.py", r),
    "split": lambda r: _cad("split.py", r),
    "sculpt": lambda r: _cad("sculpt.py", r),
    "looks": lambda r: sys.exit(subprocess.run([HG_PY, os.path.join(HERE, "looks.py")] + r, cwd=HERE).returncode),
    "remix": lambda r: _cad("remix.py", [os.path.abspath(r[0])] + r[1:] if r else []),
    "make": lambda r: _cad("make.py", r),
    "plate": lambda r: _cad("plate.py", [os.path.abspath(x) if x.endswith((".stl", ".3mf")) else x for x in r]),
}

if len(sys.argv) > 1 and sys.argv[1] in ("topo", "parts-find", "step2stl", "movecheck", "grade"):
    {"topo": cmd_topo, "parts-find": cmd_parts_find, "step2stl": cmd_step2stl, "movecheck": cmd_movecheck,
     "grade": cmd_grade}[sys.argv[1]](sys.argv[2:])
if len(sys.argv) > 1 and sys.argv[1] in NEW:
    NEW[sys.argv[1]](sys.argv[2:])

ap = argparse.ArgumentParser(prog="forge", epilog="also: topo | parts-find | step2stl | movecheck | grade | mech | fit | "
                             "flexify | preflight | export | report | heat | text3d | ar | showcase | gridfinity | photofit | split | sculpt | looks | remix | make | plate")
sub = ap.add_subparsers(dest="cmd", required=True)
r = sub.add_parser("run"); r.add_argument("part"); r.add_argument("--lane", choices=["b123d", "scad", "bpy"]); r.add_argument("--spec"); r.add_argument("--name")
r.add_argument("--no-render", action="store_true"); r.add_argument("--section"); r.add_argument("--ref"); r.add_argument("--eevee", action="store_true")
sub.add_parser("doctor")
a = ap.parse_args()
cmd_run(a) if a.cmd == "run" else cmd_doctor(a)
