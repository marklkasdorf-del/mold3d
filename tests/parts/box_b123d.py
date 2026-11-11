# b123d lane: 40x30x20 open box, 2 mm walls, 3 mm vertical fillets, 6 mm hole through the floor.
import os
from build123d import *
with BuildPart() as p:
    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))
    fillet(p.edges().filter_by(Axis.Z), radius=3)
    # hollow: remove inner pocket, leaving a 2 mm floor
    with Locations((0, 0, 2)):
        Box(36, 26, 20, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    with Locations((0, 0, 0)):
        Cylinder(3, 10, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)   # 6 mm through-hole
export_stl(p.part, os.environ["FORGE_OUT_STL"])
