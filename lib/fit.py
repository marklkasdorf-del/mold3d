"""fit.py: ONE source of truth for clearances on YOUR printer (bed/nozzle in knowledge/printer.json; defaults are for a 0.4 mm FDM, PLA).

Every generator (MechKit, flexify, gridfinity, lids...) asks fit.get("pip_gap") instead of hard-coding 0.3.
Values start as [R] research defaults; `forge fit set <key> <value> --from "<print>"` turns one into [V] verified
after a real print (the Fit Card measures pip_gap / slide_gap in one ~20 min print).

    import fit
    g = fit.get("pip_gap")            # 0.3 until calibrated
    fit.show()                        # table with [R]/[V] tags
"""
import json, os, sys, datetime

import forge_env
PATH = os.environ.get("FORGE_FIT") or os.path.join(forge_env.ROOT, "knowledge", "fit.json")

DEFAULTS = {
    # key: (value_mm, meaning, source)
    "pip_gap":    (0.30, "print-in-place rotating joint, per side (pins, gears flank, gyro rings, flexi joints)",
                   "[R] bench 2026-10-17 movers used 0.29-0.36; Printables champions 0.25"),
    "pip_vgap":   (0.30, "print-in-place vertical gap (cap/flange printed over a moving part)", "[R] = pip_gap"),
    "slide_gap":  (0.25, "sliding fit per side (lid in groove, slider in channel)", "[R] print-tolerances.md"),
    "snug_fit":   (0.15, "press-on / friction fit per side (box lids that stay on, caps)", "[R] common FDM"),
    "press_fit":  (0.05, "press/interference per side (magnets, pins pushed in)", "[R] print-tolerances.md"),
    "loose_fit":  (0.40, "drop-in / loose per side (bins in a grid, parts in a tray)", "[R] print-tolerances.md"),
    "hole_comp":  (0.15, "add to radius of small vertical holes (FDM holes print undersized)", "[R] common FDM"),
    "magnet_10x2_d": (10.4, "pocket diameter for 10x2 mm disc magnets (glue-in)", "[R] common FDM; tune with a test coupon"),
    "min_wall":   (2.0, "minimum wall for generated parts; 2.4 for structural", "[R] 0.4 nozzle = 5 perimeters; thinner reads as fragile"),
    "layer":      (0.20, "layer height of your profile (see knowledge/printer.json)", "[R] common default"),
    "nozzle":     (0.40, "nozzle diameter", "[R] edit knowledge/printer.json"),
}


def _load():
    if os.path.exists(PATH):
        try:
            return json.load(open(PATH))
        except Exception:
            pass
    return {}


def get(key):
    d = _load()
    if key in d:
        return float(d[key]["value"])
    return DEFAULTS[key][0]


def tag(key):
    d = _load()
    return "[V]" if key in d else "[R]"


def set_value(key, value, src):
    d = _load()
    d[key] = {"value": float(value), "source": src, "date": datetime.date.today().isoformat()}
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    json.dump(d, open(PATH, "w"), indent=1)


def show():
    d = _load()
    print(f"{'key':14s} {'mm':>6s}  tag  meaning / source")
    for k, (v, meaning, src) in DEFAULTS.items():
        if k in d:
            print(f"{k:14s} {d[k]['value']:6.2f}  [V]  {meaning}  <- {d[k]['source']} ({d[k]['date']})")
        else:
            print(f"{k:14s} {v:6.2f}  [R]  {meaning}  <- {src}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "show":
        show()
    elif a[0] == "set" and len(a) >= 3:
        src = a[a.index("--from") + 1] if "--from" in a else "manual"
        if a[1] not in DEFAULTS:
            sys.exit(f"unknown key {a[1]}; keys: {', '.join(DEFAULTS)}")
        set_value(a[1], a[2], src); show()
    elif a[0] == "get":
        print(get(a[1]))
    else:
        sys.exit("usage: fit.py show | get <key> | set <key> <mm> --from '<print + result>'")
