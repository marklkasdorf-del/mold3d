"""forge mech list | build <name> [k=v ...] [--out DIR] | test [names...] | ratio <name> [k=v ...] [--motion M] [--driven P] [--driver P] [--declared X]

build: builds the mechanism with fit.json clearances, runs the self-test, exports parts/*.stl + <name>.stl + mech.json
       to ./mold3d/<name>/ (or $MOLD3D_OUT) (render with bin/render, slice with your slicer).
ratio: MEASURES the reduction ratio and backlash from the geometry (no declared numbers): poses 24 drive values, frees the
       driven part and bisects for the contact-free angle interval. Writes mold3d/<name>/ratio.json. Exit 3 if it differs from the
       declared ratio by > 0.5 %.   e.g. forge mech ratio cyclo11     forge mech ratio planetary --motion mesh --driven ring --driver sun
test : builds + self-tests every registered mechanism; writes knowledge/mechkit-tests.json (the MechKit scoreboard).
"""
import importlib, json, os, sys, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import forge_env
FORGE = os.path.dirname(os.path.dirname(HERE))

REGISTRY = {
    "fitcard":   ("mechkit.fitcard",   "Fit Card: measures your printer's real print-in-place gaps (print this first)"),
    "gyro":      ("mechkit.gyro",      "nested-ring gyroscope fidget, spherical zones = collision-proof"),
    "planetary": ("mechkit.planetary", "herringbone planetary gear fidget, one plate, comes off moving"),
    "balisong":  ("mechkit.balisong",  "butterfly-knife trainer, blunt blade, print-in-place pivots"),
    "helix":     ("mechkit.helix",     "helix passthrough fidget: spiral spins down through a twisted hole"),
    "cycloidal": ("mechkit.cycloidal", "cycloidal speed reducer, N pins -> (N-1):1, four bodies, one plate (N=16 R=45 -> 15:1)"),
    "hinge":     ("mechkit.hinge",     "print-in-place pin hinge (the template: copy it for new mechanisms)"),
}


ALIASES = {"cyclo11": "cycloidal"}      # showcase piece: the default cycloidal build, output folder out/cyclo11


def _parse_kv(args):
    kw = {}
    for a in args:
        if "=" in a:
            k, v = a.split("=", 1)
            try:
                v = json.loads(v)
            except Exception:
                pass
            kw[k] = v
    return kw


def build_one(name, kw=None, out=None, verbose=True):
    from mechkit import core
    mod = importlib.import_module(REGISTRY[ALIASES.get(name, name)][0])
    t = time.time()
    m = mod.build(**(kw or {}))
    rep = core.selftest(m, verbose=verbose)
    out = out or os.path.join(forge_env.OUT, name)
    stl = core.export(m, out)
    rep["seconds"] = round(time.time() - t, 1)
    rep["stl"] = os.path.relpath(stl, FORGE)       # relative: selftest.json is shareable
    rep["meta"] = m.meta
    json.dump(rep, open(os.path.join(out, "selftest.json"), "w"), indent=1, default=str)
    return rep


def ratio_one(name, kw, out=None, motion="reduce", driven="carrier", driver="shaft", declared=None):
    from mechkit import core
    mod = importlib.import_module(REGISTRY[ALIASES.get(name, name)][0])
    m = mod.build(**(kw or {}))
    if declared is not None:
        m.meta["ratio"] = abs(declared)
        if declared < 0: m.meta["output_sign"] = -1
    t = time.time()
    r = core.measure_ratio(m, motion, driven, driver)
    r["seconds"] = round(time.time() - t, 1)
    r["name"] = m.name
    r["match"] = abs(r["measured"] - r["declared"]) <= 0.005 * abs(r["declared"])
    out = out or os.path.join(forge_env.OUT, name)
    os.makedirs(out, exist_ok=True)
    json.dump(r, open(os.path.join(out, "ratio.json"), "w"), indent=1)
    return r


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    cmd = argv[0]
    if cmd == "list":
        for k, (_, d) in REGISTRY.items():
            print(f"  {k:10s} {d}")
        print("  aliases:", ", ".join(f"{a} = {b}" for a, b in ALIASES.items()))
        return 0
    if cmd == "build":
        name = argv[1]
        out = argv[argv.index("--out") + 1] if "--out" in argv else None
        rep = build_one(name, _parse_kv(argv[2:]), out)
        print("->", rep["stl"]); return 0 if rep["ok"] else 1
    if cmd == "ratio":
        def opt(k, d=None): return argv[argv.index(k) + 1] if k in argv else d
        skip = {i for k in ("--motion", "--driven", "--driver", "--declared", "--out") if k in argv for i in (argv.index(k), argv.index(k) + 1)}
        kw = _parse_kv([a for i, a in enumerate(argv[2:], 2) if i not in skip])
        dec = opt("--declared")
        r = ratio_one(argv[1], kw, opt("--out"), opt("--motion", "reduce"), opt("--driven", "carrier"), opt("--driver", "shaft"),
                      float(dec) if dec else None)
        print(f"declared {r['declared']:+.4f}:1 ({r['declared_from']})   MEASURED {r['measured']:+.4f}:1  (out/in {r['measured_out_per_in']:+.5f})")
        print(f"backlash {r['backlash_deg']} deg = {r['backlash_arcmin']} arcmin (median of {len(r['samples'])} poses; min {r['backlash_min_deg']}, max {r['backlash_max_deg']}); {r['seconds']} s")
        print("ratio:", "MATCH" if r["match"] else "MISMATCH (> 0.5 %)")
        return 0 if r["match"] else 3
    if cmd == "test":
        names = argv[1:] or list(REGISTRY)
        board = {"date": datetime.datetime.now().isoformat(timespec="minutes"), "results": {}}
        ok_all = True
        for n in names:
            try:
                rep = build_one(n, verbose=True)
                g = rep.get("gaps") or {}
                board["results"][n] = {"ok": rep["ok"], "tightest_gap": min(g.values()) if g else None,
                                       "motions": [(r["motion"], r["sweep_worst_mm3"], r["control_jams"]) for r in rep["motions"]],
                                       "seconds": rep["seconds"]}
                ok_all &= rep["ok"]
            except Exception as e:
                board["results"][n] = {"ok": False, "error": repr(e)[:300]}; ok_all = False
                print(f"[ERROR] {n}: {e!r}")
        json.dump(board, open(os.path.join(FORGE, "knowledge", "mechkit-tests.json"), "w"), indent=1)
        print("\nMechKit scoreboard:")
        for n, r in board["results"].items():
            print(f"  {'PASS' if r['ok'] else 'FAIL'}  {n:10s} tightest gap {r.get('tightest_gap')}  {r.get('seconds', '')} s  {r.get('error', '')}")
        return 0 if ok_all else 1
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
