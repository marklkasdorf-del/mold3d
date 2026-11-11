# bpy lane: hollow tray + lid with lip + raised text (port of the audit proof). Writes combined STL
# to FORGE_OUT_STL plus separate tray.stl / lid.stl (print pose) into FORGE_PARTS_DIR for the fit check.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
import forge_bpy as fb

W, D, H, wall, lipH, clr = 60.0, 40.0, 25.0, 2.0, 3.0, 0.3
fb.reset()
# tray (x centred at 0)
tray = fb.box("tray", W, D, H, 0)
fb.boolean(tray, fb.box("cav", W - 2 * wall, D - 2 * wall, H, wall), "DIFFERENCE")
# lid built at origin: plate z0..wall, lip hanging below, raised text on top; then moved beside the tray
lid = fb.box("lid", W, D, wall, 0)
lip = fb.box("lip", W - 2 * wall - 2 * clr, D - 2 * wall - 2 * clr, lipH, -lipH + 0.01)
fb.boolean(lip, fb.box("lc", W - 4 * wall - 2 * clr, D - 4 * wall - 2 * clr, lipH + 1, -lipH - 0.5), "DIFFERENCE")
fb.boolean(lid, lip, "UNION")
fb.boolean(lid, fb.text("HELLO", size=9, extrude=0.4, z=wall), "UNION", solver="EXACT")
lid.location = (W + 10, 0, lipH)
bpy = fb.bpy
bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.transform_apply(location=True)
pd = fb.parts_dir()
fb.export([tray], os.path.join(pd, "tray.stl"))
fb.export([lid], os.path.join(pd, "lid.stl"))
fb.export([tray, lid], fb.out_stl())
