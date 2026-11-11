"""MechKit template: copy to lib/mechkit/<name>.py, register it in lib/mechkit/cli.py REGISTRY, then
`forge mech build <name>`. Example below = a print-in-place PIN HINGE that folds 0..150 deg (passes as-is).

Recipe for ANY mechanism:
 1. Model every part in its ASSEMBLED pose (build123d), clearances from fit.get(...) only.
 2. Declare each motion as Moves (rot/trans/helix with axis + pivot + ratio). Coupled parts = several Moves.
 3. Add a CONTROL: a wrong motion that must collide somewhere along its path (proves the parts engage).
 4. selftest(): static overlaps 0, sweep clear, control jams, gaps ~= the fit value. Then forge render + preflight.
Design tricks that make collisions impossible by construction:
 * surfaces that move against each other = arcs/spheres centred on the pivot (gap constant at every angle)
 * keep a mover's whole swept volume on its own side of a plane (balisong pivot placement)
 * captured pins = 45-deg cones (true 45: base radius > length), socket = pin offset by gap*sqrt(2) radially
"""
import os, sys
from build123d import *
from .core import Mech, Motion, Move

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fit
from mechkit.fitcard import hinge          # the Fit Card's proven flat hinge


def build(width=30.0, leaf=20.0, gap=None):
    g = fit.get("pip_vgap") if gap is None else gap      # horizontal pins sag -> the hinge row of the Fit Card
    A, B, rk = hinge(g, w=width, leaf=leaf)
    parts = {"leafA": A, "leafB": B}
    fold = Motion("fold", (0, 150), [Move("leafB", "rot", axis=(1, 0, 0), pivot=(0, 0, rk))],
                  control=[Move("leafB", "trans", axis=(1, 0, 0), amount=1.5)],    # sliding along the pin must jam
                  steps=13, note="flap folds up and over")
    return Mech("hinge", parts, ["leafA"], [fold], meta={"gap": g})
