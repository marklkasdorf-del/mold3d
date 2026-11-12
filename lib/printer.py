"""printer: the active printer profile (bed, nozzle, layer height, optional slicer command).

Profile = json file, default knowledge/printer.json; override with FORGE_PRINTER=/path/to/profile.json.
Examples live in knowledge/printers/. Everything that used to hard-code a bed size reads this.

    import printer
    printer.bed()          # (220.0, 220.0, 250.0)
    printer.get("nozzle")  # 0.4
    printer.slice_stats(stl, supports="auto")   # (time_str, grams) via your slicer command, or (None, None)

Slicer hook: set "slicer_cmd" in the profile or env FORGE_SLICER_CMD to a shell command template using
{stl} and {supports} (on|off|auto). It must print lines containing
    printing time: <text>
    total filament used [g]: <number>
Anything else (or no command) = forge does NOT slice; use your slicer of choice on the STL.
"""
import json, os, re, subprocess
import forge_env

DEFAULT = {"name": "generic 220 FDM", "bed": [220.0, 220.0, 250.0], "nozzle": 0.4, "layer": 0.2,
           "material": "PLA", "slicer_cmd": "",
           "support_angle": 30, "support_trap_gap": 2.0}   # slicer auto-support threshold (deg from horizontal; Orca default 30); max gap a support would bridge-fill


def _path():
    return os.environ.get("FORGE_PRINTER") or os.path.join(forge_env.ROOT, "knowledge", "printer.json")


def load():
    d = dict(DEFAULT)
    try:
        d.update(json.load(open(_path())))
    except Exception:
        pass
    return d


def get(key):
    if key == "support_angle" and os.environ.get("FORGE_SUPPORT_ANGLE"):
        return float(os.environ["FORGE_SUPPORT_ANGLE"])
    return load()[key]


def bed():
    return tuple(float(v) for v in load()["bed"])


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
