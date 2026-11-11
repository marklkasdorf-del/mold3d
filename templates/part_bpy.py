"""forge starter: Blender bpy part (lane bpy: organic / mesh / text-heavy). Blender 5.2 LTS.
Run:  bin/forge run part_bpy.py --lane bpy --name mypart     
Raw:  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python part_bpy.py
Units: 1 Blender unit = 1 mm (scene unit scale 0.001, export_scale 1.0). Origin: object bbox bottom-centre on Z=0.
Booleans: operands MUST share one coordinate frame -> build everything at the origin, translate last.
Example: rounded slab + engraved text via EXACT boolean + weld + voxel-free manifold check.
"""
import os, sys
import bpy, bmesh
from mathutils import Vector

# ---------------- PARAMETERS (mm) ----------------
LENGTH, WIDTH, THICK = 60.0, 30.0, 4.0
BEVEL        = 1.0            # edge bevel (chamfer-like, 1 segment) on slab
TEXT         = "FORGE"
TEXT_SIZE    = 8.0
TEXT_DEPTH   = 0.8            # engrave depth, mm
TEXT_FONT_MIN_STROKE = 0.8    # text strokes thinner than 2 nozzle widths (0.8) will not print crisply
EPS          = 0.01

# ---------------- helpers ----------------
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.unit_settings.system = 'METRIC'
    s.unit_settings.scale_length = 0.001      # 1 BU = 1 mm
    s.unit_settings.length_unit = 'MILLIMETERS'

def select_only(obj):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def apply_modifier(obj, name):
    select_only(obj)
    bpy.ops.object.modifier_apply(modifier=name)

def make_slab():
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.active_object
    o.name = "slab"
    o.scale = (LENGTH, WIDTH, THICK)
    bpy.ops.object.transform_apply(scale=True)
    o.location = (0, 0, THICK / 2)                      # bottom on Z=0
    bpy.ops.object.transform_apply(location=True)
    m = o.modifiers.new("bev", 'BEVEL'); m.width = BEVEL; m.segments = 1; m.limit_method = 'ANGLE'
    apply_modifier(o, "bev")
    return o

def make_text_cutter():
    bpy.ops.object.text_add()
    t = bpy.context.active_object
    t.name = "text_cutter"
    t.data.body = TEXT
    t.data.size = TEXT_SIZE
    t.data.extrude = (TEXT_DEPTH + 2 * EPS) / 2         # extrude is half-depth each side of the plane
    t.data.align_x = 'CENTER'; t.data.align_y = 'CENTER'
    select_only(t)
    bpy.ops.object.convert(target='MESH')               # text -> mesh is NON-MANIFOLD: weld + fix normals
    t = bpy.context.active_object
    bm = bmesh.new(); bm.from_mesh(t.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(t.data); bm.free()
    t.location = (0, 0, THICK - TEXT_DEPTH / 2 + EPS)   # sits in the top face, cutter pokes out by EPS
    return t

def boolean(target, cutter, op='DIFFERENCE', solver='EXACT'):
    """EXACT, not MANIFOLD, whenever an operand came from text/curves (MANIFOLD silently drops non-manifold operands)."""
    v0 = mesh_volume(target)
    m = target.modifiers.new("bool", 'BOOLEAN'); m.operation = op; m.solver = solver; m.object = cutter
    apply_modifier(target, "bool")
    bpy.data.objects.remove(cutter, do_unlink=True)
    return v0, mesh_volume(target)

def mesh_volume(obj):
    bm = bmesh.new(); bm.from_mesh(obj.data); v = bm.calc_volume(signed=True); bm.free(); return abs(v)

def non_manifold_edges(obj):
    bm = bmesh.new(); bm.from_mesh(obj.data); n = sum(1 for e in bm.edges if not e.is_manifold); bm.free(); return n

def bbox(obj):
    xs = [v.co.x for v in obj.data.vertices]; ys = [v.co.y for v in obj.data.vertices]; zs = [v.co.z for v in obj.data.vertices]
    return Vector((max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))), min(zs)

def export_stl(obj, path):
    select_only(obj)
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, apply_modifiers=True, global_scale=1.0)

# ---------------- BUILD ----------------
def build():
    reset_scene()
    slab = make_slab()
    cutter = make_text_cutter()
    v0, v1 = boolean(slab, cutter)
    assert v1 < v0 - 1.0, f"text boolean dropped (volume {v0:.1f}->{v1:.1f})"       # silent-drop guard
    assert non_manifold_edges(slab) == 0, "non-manifold edges after boolean"
    size, zmin = bbox(slab)
    assert abs(zmin) < 1e-3, f"part not on Z=0 ({zmin})"
    assert abs(size.x - LENGTH) < 0.05 and abs(size.y - WIDTH) < 0.05 and abs(size.z - THICK) < 0.05, size
    return slab

if __name__ == "__main__":
    part = build()
    out = os.environ.get("FORGE_OUT_STL", os.path.join(os.environ.get("TMPDIR", "/tmp"), "part_bpy.stl"))
    export_stl(part, out)
    print(f"OK {out} vol={mesh_volume(part):.0f}mm3 bbox={tuple(round(v,2) for v in bbox(part)[0])}")
