"""Blender (Workbench) render of a risk-coloured PLY from preflight --heat. Run via bin/blender_py.
args after '--': <ply> <out.png> [--w 1100 --h 800]
Colours: red = overhang needing support, yellow = borderline 45 deg, blue = bed contact, grey = fine."""
import bpy, sys, math
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
ply, out = argv[0], argv[1]
W = int(argv[argv.index("--w") + 1]) if "--w" in argv else 1100
H = int(argv[argv.index("--h") + 1]) if "--h" in argv else 800
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.wm.ply_import(filepath=ply)
ob = bpy.context.selected_objects[0]
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light = "STUDIO"; sh.color_type = "VERTEX"; sh.show_shadows = True; sh.show_cavity = True
sh.cavity_type = "BOTH"
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.render.film_transparent = False
world = bpy.data.worlds.new("w"); sc.world = world
world.color = (0.94, 0.925, 0.89)
sh.background_type = "WORLD"
cs = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
mn = Vector((min(c.x for c in cs), min(c.y for c in cs), min(c.z for c in cs)))
mx = Vector((max(c.x for c in cs), max(c.y for c in cs), max(c.z for c in cs)))
ctr = (mn + mx) / 2; size = (mx - mn).length
cam_data = bpy.data.cameras.new("cam"); cam_data.type = "ORTHO"; cam_data.ortho_scale = size * 1.05
cam = bpy.data.objects.new("cam", cam_data); sc.collection.objects.link(cam); sc.camera = cam
views = {"iso": Vector((1, -1, 0.8)), "under": Vector((1, -1, -0.9))}
for name, d in views.items():
    d = d.normalized(); cam.location = ctr + d * size * 2
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = out.replace(".png", f"_{name}.png")
    bpy.ops.render.render(write_still=True)
print("wrote", out)
