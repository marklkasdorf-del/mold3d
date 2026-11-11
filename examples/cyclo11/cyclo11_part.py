"""CYCLO-11 as a `forge run` part (build123d lane): builds the MechKit cycloidal reducer and hands forge the assembled STL
plus one STL per body, so verify / movecheck / preflight / the annotated sheet all run on exactly what gets printed.
    forge run examples/cyclo11/cyclo11_part.py --name cyclo11 --spec examples/cyclo11/spec.json
(The self-test, ratio and backlash numbers come from `forge mech build cyclo11` / `forge mech ratio cyclo11`.)"""
import os, shutil, sys, tempfile
sys.path.insert(0, os.environ["FORGE_LIB"])
from build123d import Compound          # noqa: F401  (also marks this file as the build123d lane)
from mechkit import cycloidal, core

m = cycloidal.build()
tmp = tempfile.mkdtemp()
core.export(m, tmp)
shutil.copy(os.path.join(tmp, f"{m.name}.stl"), os.environ["FORGE_OUT_STL"])
for f in os.listdir(os.path.join(tmp, "parts")):
    shutil.copy(os.path.join(tmp, "parts", f), os.path.join(os.environ["FORGE_PARTS_DIR"], f))
