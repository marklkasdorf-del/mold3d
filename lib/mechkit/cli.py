"""forge mech list | build <name> [k=v ...] [--out DIR] | test [names...]

build: builds the mechanism with fit.json clearances, runs the self-test, exports parts/*.stl + <name>.stl + mech.json
       to <skill>/out/<name>/ (render with bin/render, slice with your slicer).
test : builds + self-tests every registered mechanism; writes knowledge/mechkit-tests.json (the MechKit scoreboard).
"""
import importlib, json, os, sys, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FORGE = os.path.dirname(os.path.dirname(HERE))

REGISTRY = {
    "fitcard":   ("mechkit.fitcard",   "Fit Card: measures your printer's real print-in-place gaps (print this first)"),
    "gyro":      ("mechkit.gyro",      "nested-ring gyroscope fidget, spherical zones = collision-proof"),
    "planetary": ("mechkit.planetary", "herringbone planetary gear fidget, one plate, comes off moving"),
    "balisong":  ("mechkit.balisong",  "butterfly-knife trainer, blunt blade, print-in-place pivots"),
    "helix":     ("mechkit.helix",     "helix passthrough fidget: spiral spins down through a twisted hole"),
    "hinge":     ("mechkit.hinge",     "print-in-place pin hinge (the template: copy it for new mechanisms)"),
}


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
    mod = importlib.import_module(REGISTRY[name][0])
    t = time.time()
    m = mod.build(**(kw or {}))
    rep = core.selftest(m, verbose=verbose)
    out = out or os.path.join(FORGE, "out", name)
    stl = core.export(m, out)
    rep["seconds"] = round(time.time() - t, 1)
    rep["stl"] = stl
    rep["meta"] = m.meta
    json.dump(rep, open(os.path.join(out, "selftest.json"), "w"), indent=1, default=str)
    return rep


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    cmd = argv[0]
    if cmd == "list":
        for k, (_, d) in REGISTRY.items():
            print(f"  {k:10s} {d}")
        return 0
    if cmd == "build":
        name = argv[1]
        out = argv[argv.index("--out") + 1] if "--out" in argv else None
        rep = build_one(name, _parse_kv(argv[2:]), out)
        print("->", rep["stl"]); return 0 if rep["ok"] else 1
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
