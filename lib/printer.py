"""printer: the active printer profile (bed, nozzle, layer, the preflight thresholds, optional slicer command), each number with a source.

Profile = json file, default knowledge/printer.json; override with FORGE_PRINTER=/path/to/profile.json.
Ready-made profiles live in knowledge/printers/ (one per printer, every number with a `sources` line).
Everything that used to hard-code a bed size or a threshold reads this.

    import printer
    printer.bed()                 # (220.0, 220.0, 250.0)
    printer.get("bridge_mm")      # 18.0  (longest unsupported span that still prints)
    printer.source("bridge_mm")   # where that number came from
    printer.slice_stats(stl, supports="auto")   # (time_str, grams) via your slicer command, or (None, None)

CLI:  forge printer            show the active profile, every threshold with its source
      forge printer list       the ready-made profiles
      forge printer use NAME   copy knowledge/printers/NAME.json over the active profile

Slicer hook: set "slicer_cmd" in the profile or env FORGE_SLICER_CMD to a shell command template using
{stl} and {supports} (on|off|auto). It must print lines containing
    printing time: <text>
    total filament used [g]: <number>
Anything else (or no command) = forge does NOT slice; use your slicer of choice on the STL.
"""
import glob, json, os, re, shutil, subprocess, sys
import forge_env

# The generic profile. Every threshold preflight / verify use is here, with its source, so "why 18?" has an answer.
DEFAULT = {"name": "generic 220 FDM", "bed": [220.0, 220.0, 250.0], "nozzle": 0.4, "layer": 0.2,
           "material": "PLA", "slicer_cmd": "",
           "support_angle": 30,          # slope from horizontal (deg) below which a slicer auto-supports a face
           "support_trap_gap": 2.0,      # biggest gap (mm) an auto support would fill between two bodies
           "bridge_mm": 18,              # longest unsupported span anchored on two sides that still prints (mm)
           "overhang_deg": 45,           # steepest overhang from horizontal that prints without support (deg)
           "min_wall_mm": 1.2,           # thinnest wall that prints at all (mm)
           "first_layer_fuse_mm": 0.35,  # first-layer gap below which elephant foot welds two bodies (mm)
           "overhang_area_mm2": 120}     # unsupported overhang area (not bridges) a part may carry before supports are demanded

DEFAULT_SOURCES = {
    "bed": "generic: 220 x 220 x 250 mm, the common bedslinger class. Pick a real profile (forge printer list) or edit.",
    "nozzle": "0.4 mm, the stock nozzle on nearly every consumer FDM printer.",
    "layer": "0.20 mm, the usual stock-profile layer height. Edit if your profile differs.",
    "support_angle": "OrcaSlicer support_threshold_angle default = 30 deg (src/libslic3r/PrintConfig.cpp). Other slicers' defaults are UNVERIFIED here.",
    "support_trap_gap": "Mold3D house value [R]: the gap an auto support would fill and weld; suite fixtures 0.3 mm fires, 5 mm does not.",
    "bridge_mm": "Mold3D house value [R] from the 2026-10 bench fixtures (10 mm bridge GO, 30 mm needs supports). OrcaSlicer's max_bridge_length default is 10 mm (PrintConfig.cpp).",
    "overhang_deg": "Prusa Knowledge Base, 'Modeling with 3D printing in mind': 45 to 60 deg prints cleanly depending on nozzle and settings (https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135). 45 is the safe end.",
    "min_wall_mm": "3 perimeters at a 0.4 mm nozzle [R]. Prusa KB (same article): walls thinner than one perimeter (~0.45 mm) are not printable. 1.2 mm is the house minimum that survives handling.",
    "first_layer_fuse_mm": "Mold3D house value [R] for first-layer gaps that elephant foot welds; Kobra X Fit Card 2026-11-13 freed 0.20 mm spinners (knowledge/fit-table.md), so it is conservative.",
    "overhang_area_mm2": "Mold3D house value [R]: the suite's 10 x 10 mm roof (100 mm2) prints without supports, a 30 x 10 mm one (300 mm2) does not; 30 to 120 mm2 is only noted.",
}
THRESHOLDS = ("support_angle", "support_trap_gap", "bridge_mm", "overhang_deg", "min_wall_mm", "first_layer_fuse_mm", "overhang_area_mm2")
PROFILES_DIR = os.path.join(forge_env.ROOT, "knowledge", "printers")


def _path():
    return os.environ.get("FORGE_PRINTER") or os.path.join(forge_env.ROOT, "knowledge", "printer.json")


def load():
    d = dict(DEFAULT)
    d["sources"] = dict(DEFAULT_SOURCES)
    try:
        u = json.load(open(_path()))
        srcs = u.pop("sources", {}) or {}
        d.update(u)
        d["sources"].update(srcs)
        # a key the user changed without a source line is UNVERIFIED, not silently credited to the generic source
        for k in list(DEFAULT) + ["bed"]:
            if k in u and k not in srcs and u[k] != DEFAULT.get(k) and k not in ("name", "slicer_cmd", "material"):
                d["sources"][k] = "UNVERIFIED: set in this profile without a source line"
    except Exception:
        pass
    return d


def get(key):
    if key == "support_angle" and os.environ.get("FORGE_SUPPORT_ANGLE"):
        return float(os.environ["FORGE_SUPPORT_ANGLE"])
    v = load()[key]
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v


def source(key):
    return load()["sources"].get(key, "UNVERIFIED")


def bed():
    return tuple(float(v) for v in load()["bed"])


def limits():
    """every preflight threshold in one dict (goes into preflight.json so a verdict says what it was judged against)."""
    d = load()
    return {k: float(d[k]) for k in THRESHOLDS} | {"layer": float(d["layer"]), "bed": [float(v) for v in d["bed"]]}


def profiles():
    out = []
    for f in sorted(glob.glob(os.path.join(PROFILES_DIR, "*.json"))):
        try:
            out.append((os.path.basename(f)[:-5], json.load(open(f)).get("name", "?"), f))
        except Exception:
            pass
    return out


def show():
    d = load()
    p = _path()
    print(f"printer: {d['name']}   ({p if os.path.exists(p) else 'no profile file, generic defaults; forge printer use <name>'})")
    print(f"  bed {d['bed'][0]:g} x {d['bed'][1]:g} x {d['bed'][2]:g} mm, nozzle {d['nozzle']:g}, layer {d['layer']:g}, {d['material']}"
          + (f", slicer hook set" if d.get("slicer_cmd") else ", no slicer hook (no time/grams in reports)"))
    print(f"  bed source: {d['sources'].get('bed', 'UNVERIFIED')}")
    print("  thresholds preflight judges against:")
    units = {"support_angle": "deg", "overhang_deg": "deg", "overhang_area_mm2": "mm2"}
    for k in THRESHOLDS:
        print(f"    {k:<20} {d[k]:>6g} {units.get(k, 'mm'):<4} {d['sources'].get(k, 'UNVERIFIED')}")
    if d.get("notes"):
        print(f"  note: {d['notes']}")


def use(name):
    cands = {b: f for b, _, f in profiles()}
    if name not in cands:
        sys.exit(f"no profile called '{name}'. Choices: {', '.join(sorted(cands))}  (or edit {_path()} by hand)")
    dst = _path()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy(cands[name], dst)
    print(f"now using {json.load(open(dst))['name']}  ->  {dst}")


def slice_stats(stl, supports="auto", timeout=3600):
    cmd = os.environ.get("FORGE_SLICER_CMD") or load().get("slicer_cmd") or ""
    if not cmd:
        return None, None
    try:
        out = subprocess.run(cmd.format(stl=stl, supports=supports), shell=True, capture_output=True,
                             text=True, timeout=timeout).stdout
    except Exception:
        return None, None
    t = g = None
    for line in out.splitlines():
        if "printing time" in line:
            t = line.split(":", 1)[1].strip()
        if "total filament used [g]" in line:
            m = re.search(r"[\d.]+", line.split(":", 1)[1])
            g = float(m.group()) if m else None
    return t, g


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "show":
        show()
    elif a[0] == "list":
        for b, n, _ in profiles():
            print(f"  {b:<20} {n}")
        print("\nforge printer use <name> picks one.")
    elif a[0] == "use" and len(a) == 2:
        use(a[1])
    else:
        sys.exit("usage: forge printer [show | list | use <name>]")
