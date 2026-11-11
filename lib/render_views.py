"""Blender headless renderer for forge. Run via bin/blender_py.
args after '--':  <stl> <outdir> [--section z=10] [--eevee] [--w 780] [--h 600]
Writes <outdir>/raw_<view>.png (transparent bg, no annotations) and <outdir>/cams.json
(camera basis + scale so annotate.py can project grid/rulers exactly).
Units: 1 Blender unit = 1 mm."""
import bpy, bmesh, sys, os, json, math
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:]
stl, outdir = argv[0], argv[1]
opt = {"section": None, "eevee": False, "w": 780, "h": 600}
i = 2
while i < len(argv):
    if argv[i] == "--section": opt["section"] = argv[i + 1]; i += 2
    elif argv[i] == "--eevee": opt["eevee"] = True; i += 1
    elif argv[i] == "--w": opt["w"] = int(argv[i + 1]); i += 2
    elif argv[i] == "--h": opt["h"] = int(argv[i + 1]); i += 2
    else: raise SystemExit(f"render_views: unknown arg {argv[i]}")
W, H = opt["w"], opt["h"]
os.makedirs(outdir, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.wm.stl_import(filepath=stl)
obj = bpy.context.selected_objects[0]
bpy.context.view_layer.objects.active = obj
obj.data.materials.clear()
mat_body = bpy.data.materials.new("body"); mat_body.diffuse_color = (0.88, 0.91, 0.96, 1)
mat_cut = bpy.data.materials.new("cut"); mat_cut.diffuse_color = (1.0, 0.62, 0.2, 1)
obj.data.materials.append(mat_body); obj.data.materials.append(mat_cut)
for p in obj.data.polygons: p.material_index = 0

def bbox_world(o):
    cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return Vector((min(c.x for c in cs), min(c.y for c in cs), min(c.z for c in cs))), Vector((max(c.x for c in cs), max(c.y for c in cs), max(c.z for c in cs)))

bmin0, bmax0 = bbox_world(obj)          # bbox of the FULL part (reported dims always use this)
meta = {"bbox_min": list(bmin0), "bbox_max": list(bmax0), "section": None, "warnings": []}

# ---- optional section: boolean-cut away one side, colour the cap faces
sec_axis = None
if opt["section"]:
    ax, val = opt["section"].lower().split("="); val = float(val); axi = "xyz".index(ax)
    keep_low = ax != "y"                  # camera sits on +x / +z side; for y on -y side (keep y>val)
    big = 10000.0
    bpy.ops.mesh.primitive_cube_add(size=1)
    cut = bpy.context.object
    cut.scale = (big, big, big)
    loc = [0, 0, 0]; loc[axi] = val + (big / 2 if keep_low else -big / 2)
    cut.location = loc
    bpy.ops.object.transform_apply(location=True, scale=True)
    v0 = None
    for solver in ("MANIFOLD", "EXACT"):
        bm = bmesh.new(); bm.from_mesh(obj.data); vol0 = bm.calc_volume(); bm.free()
        mod = obj.modifiers.new("cut", "BOOLEAN"); mod.operation = "DIFFERENCE"; mod.object = cut; mod.solver = solver
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier="cut")
        smin, smax = bbox_world(obj)
        got = (smax[axi] if keep_low else smin[axi])
        if len(obj.data.polygons) > 0 and abs(got - val) < 0.5:
            break
        meta["warnings"].append(f"section boolean with {solver} did not cut cleanly")
        # reload and retry with next solver
        bpy.ops.object.delete(); bpy.ops.wm.stl_import(filepath=stl); obj = bpy.context.selected_objects[0]
        obj.data.materials.append(mat_body); obj.data.materials.append(mat_cut)
        bpy.context.view_layer.objects.active = obj
    else:
        meta["warnings"].append("SECTION FAILED: showing uncut part")
    bpy.data.objects.remove(cut, do_unlink=True)
    me = obj.data
    ncap = 0
    for p in me.polygons:
        on_plane = all(abs(me.vertices[v].co[axi] - val) < 1e-3 for v in p.vertices)
        if on_plane:
            p.material_index = 1; ncap += 1
    meta["section"] = {"axis": ax, "value": val, "keep_low": keep_low, "cap_faces": ncap}
    if ncap == 0:
        meta["warnings"].append(f"section plane {opt['section']} misses the part (bbox {[round(x,1) for x in bmin0]}..{[round(x,1) for x in bmax0]})")
    sec_axis = (axi, val, keep_low)

# ---- shading
sc.render.engine = "BLENDER_EEVEE" if opt["eevee"] else "BLENDER_WORKBENCH"
sc.render.film_transparent = True
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.render.resolution_percentage = 100
sc.view_settings.view_transform = "Standard"
if not opt["eevee"]:
    sh = sc.display.shading
    sh.light = "STUDIO"; sh.color_type = "MATERIAL"
    sh.show_cavity = True; sh.cavity_type = "BOTH"; sh.cavity_ridge_factor = 3.5; sh.cavity_valley_factor = 3.0
    sh.show_shadows = True; sh.shadow_intensity = 0.55
    sc.display.light_direction = (-0.5, -0.6, 0.65)
    sh.show_object_outline = True; sh.object_outline_color = (0.05, 0.05, 0.08)
    sh.show_specular_highlight = False
    sc.display.render_aa = "8"
else:
    for m in (mat_body, mat_cut): m.use_nodes = False
    sun = bpy.data.lights.new("sun", "SUN"); sun.energy = 3.0; sun.angle = math.radians(8)
    so = bpy.data.objects.new("sun", sun); sc.collection.objects.link(so)
    so.rotation_euler = (math.radians(50), 0, math.radians(35))
    sc.world = bpy.data.worlds.new("w"); sc.world.color = (0.8, 0.8, 0.8)
    sc.eevee.taa_render_samples = 24

# ---- cameras
cam_d = bpy.data.cameras.new("cam"); cam_d.type = "ORTHO"; cam_d.sensor_fit = "HORIZONTAL"
cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam); sc.camera = cam
smin, smax = bbox_world(obj)
if sec_axis is None: smin, smax = bmin0, bmax0
center = (smin + smax) / 2
diag = (smax - smin).length
corners = [Vector((x, y, z)) for x in (smin.x, smax.x) for y in (smin.y, smax.y) for z in (smin.z, smax.z)]

def basis(d):
    d = Vector(d).normalized()
    up = Vector((0, 0, 1)) if abs(d.z) < 0.999 else Vector((0, 1, 0))
    yv = (up - d * up.dot(d)).normalized()
    xv = yv.cross(d).normalized()
    return xv, yv, d

TOP, BOT = 56, 62        # px reserved for header / footer annotation
def frame(name, d):
    xv, yv, dv = basis(d)
    xs = [(c - center).dot(xv) for c in corners]; ys = [(c - center).dot(yv) for c in corners]
    w = max(xs) - min(xs); h = max(ys) - min(ys)
    w = max(w, 1e-3); h = max(h, 1e-3)
    m = 0.07
    s = min(W * (1 - 2 * m) / w, (H - TOP - BOT) * 0.96 / h)      # px per mm
    mx = (max(xs) + min(xs)) / 2; my = (max(ys) + min(ys)) / 2
    # place projected bbox centre at pixel (W/2, TOP + (H-TOP-BOT)/2)
    cy_px = TOP + (H - TOP - BOT) / 2
    shift_y_mm = (H / 2 - cy_px) / s
    c = center + xv * mx + yv * (my + shift_y_mm)
    cam.location = c + dv * (diag * 3 + 50)
    cam.matrix_world = Matrix(((xv.x, yv.x, dv.x, cam.location.x), (xv.y, yv.y, dv.y, cam.location.y), (xv.z, yv.z, dv.z, cam.location.z), (0, 0, 0, 1)))
    cam_d.ortho_scale = W / s
    cam_d.clip_start = 1.0; cam_d.clip_end = diag * 6 + 200
    return {"name": name, "dir": list(dv), "right": list(xv), "up": list(yv), "px_per_mm": s,
            "ortho_center": list(c), "W": W, "H": H}

views = {"iso": (1, -1, 0.85), "iso_back": (-1, 1, 0.85), "front": (0, -1, 0.0), "side": (1, 0, 0.0),
         "oblique_top": (0.35, -1, 0.75), "oblique_bottom": (0.5, -1, -0.8)}
if sec_axis:
    axi, val, keep_low = sec_axis
    n = [0, 0, 0]; n[axi] = 1 if keep_low else -1
    flat = tuple(n)
    if axi == 2: obl = (0.35, -0.7, 1.0)
    elif axi == 0: obl = (1.0, -0.55, 0.55)
    else: obl = (0.5, -1.0, 0.6)
    views = {"section_oblique": obl, "section_flat": flat, "oblique_top": views["oblique_top"], "iso": views["iso"]}
cams = {}
for name, d in views.items():
    cams[name] = frame(name, d)
    sc.render.filepath = os.path.join(outdir, f"raw_{name}.png")
    bpy.ops.render.render(write_still=True)
meta["views"] = cams
json.dump(meta, open(os.path.join(outdir, "cams.json"), "w"), indent=1)
print("RENDER_DONE", list(cams), meta["warnings"])
