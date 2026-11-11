# organic-and-mesh.md — the honest lane for organic shapes (Blender, no sculpting)

## Honest verdict first
Claude is weak at organic/character/creature modeling: "organics and clean topology are where Claude fails" (MindStudio); a dragon from ~80 primitives "looked like concept art, not a printable mesh" (TojQChim9mM); nobody reported complex organic or articulated mechanisms working (research reddit.md §5). Generative image-to-3D (Meshy/Tripo/Hyper3D/Adam/Astra) gives mesh-only decorative toys with wrong text and no real dimensions (NjybDaUOKEg).
**Default for organic asks: say this out loud in one sentence, then offer (1) find the best existing model on a model site, (2) remix a downloaded STL, (3) local text-to-3D (`forge text3d`), (4) the simple blobby/stylised approaches below.**

## What this lane CAN do reliably (all verified in Blender 5.2.1, headless, 2026-10-14)
Stylised blobs, creature bodies from ball-clusters, organic stands/planters/cable-guides, branching stick-figure volumes, textured reliefs, "make this STL smoother/watertight/thicker/thinner".
Every recipe: units 1 BU = 1 mm; build at origin; finish with voxel remesh -> decimate -> numeric check -> `wm.stl_export`. Run via `forge run part.py --lane bpy` (unsandboxed).
Shared helpers (copy from templates/part_bpy.py): `select_only`, `apply_modifier`, `mesh_volume`, `non_manifold_edges`.

### A. Metaballs -> mesh (blobby bodies, soft joins). Result: 2136 verts, 0 non-manifold, 2681 mm3
```python
mb = bpy.data.metaballs.new("mb"); ob = bpy.data.objects.new("mb", mb); bpy.context.scene.collection.objects.link(ob)
mb.resolution = 1.0; mb.threshold = 0.6                    # resolution = mm cell size; lower = finer, slower
for (x, y, z, r) in [(0,0,0,12), (14,0,2,9), (-12,3,-1,8), (0,14,0,7)]:
    e = mb.elements.new(type='BALL'); e.co = (x, y, z); e.radius = r      # radius in mm
select_only(ob); bpy.ops.object.convert(target='MESH')
```
Types other than `'BALL'` exist (`'CAPSULE'`, `'PLANE'`, `'ELLIPSOID'`, `'CUBE'`): introspect `bpy.types.MetaElement.bl_rna.properties['type'].enum_items`.

### B. Voxel remesh (watertight by construction). 3490 faces, 0 non-manifold, volume 2681 -> 2665
```python
obj.data.remesh_voxel_size = 0.8      # mm; rule: <= 1/2 smallest feature to keep
select_only(obj); bpy.ops.object.voxel_remesh()
```
Run it on ANY messy union before export. It rounds sharp edges by roughly one voxel: do not use on fit-critical flat faces; use b123d for those and merge.

### C. Decimate (shrink file / triangle count). 3490 -> 2154 faces, still 0 non-manifold
```python
d = obj.modifiers.new("dec", 'DECIMATE'); d.ratio = 0.4
select_only(obj); bpy.ops.object.modifier_apply(modifier="dec")
```
Re-check volume (2665 -> 2660) and non-manifold count after.

### D. Skin modifier: stick-figure skeleton -> volumetric body (branches, tentacles, stands). 952 faces, 0 non-manifold, 1353 mm3
```python
me = bpy.data.meshes.new("sk"); o = bpy.data.objects.new("sk", me); bpy.context.scene.collection.objects.link(o)
bm = bmesh.new()
vs = [bm.verts.new(p) for p in [(0,0,0), (0,0,20), (10,0,30), (-10,0,30), (0,0,40)]]
for a, b in [(0,1), (1,2), (1,3), (1,4)]: bm.edges.new((vs[a], vs[b]))
bm.to_mesh(me); bm.free()
o.modifiers.new("skin", 'SKIN')
for v in o.data.skin_vertices[0].data: v.radius = (3, 3)        # per-vertex half-thickness (x,y) in mm
ss = o.modifiers.new("ss", 'SUBSURF'); ss.levels = 2; ss.render_levels = 2
select_only(o)
for n in ("skin", "ss"): bpy.ops.object.modifier_apply(modifier=n)
```
Set per-vertex radii bigger at the "body", smaller at the tips. Branch joints are where it can pinch: check min wall with `forge/bin/verify`.

### E. Displacement relief (texture/terrain/bark on a plate). z range 0.47-2.64 mm from `strength=3`
```python
bpy.ops.mesh.primitive_grid_add(x_subdivisions=60, y_subdivisions=60, size=40)
g = bpy.context.active_object
tex = bpy.data.textures.new("n", 'CLOUDS'); tex.noise_scale = 0.4
dm = g.modifiers.new("disp", 'DISPLACE'); dm.texture = tex; dm.strength = 3.0; dm.mid_level = 0.0
select_only(g); bpy.ops.object.modifier_apply(modifier="disp")
```
Subdivision count controls detail: features smaller than ~0.8 mm will not print.

### F. Thicken an open surface into a printable solid (Solidify). 0 non-manifold, 4082 mm3 for the 40x40 relief
```python
sol = g.modifiers.new("sol", 'SOLIDIFY'); sol.thickness = -2.0; sol.offset = -1; sol.use_even_offset = True
select_only(g); bpy.ops.object.modifier_apply(modifier="sol")
```
Thickness >= 1.6 mm for anything handled (sturdy). Negative thickness + offset -1 grows downward from the surface, so Z=0 stays near the base: re-seat afterwards (`obj.location.z -= min_z`, apply).

### G. Edit/clean a downloaded STL (remix path)
`bpy.ops.wm.stl_import(filepath=...)` -> scale/boolean/bevel/`voxel_remesh` -> `wm.stl_export`. This is the "edit an existing STL by code, not by remodelling" approach that "went perfectly" (evilduck, HN 49676577). To cut a hole in a downloaded part, build the cutter at the same origin and use `solver='EXACT'`; then verify volume dropped by ~ cutter volume.

## Post-processing checklist (every organic export)
1. `remove_doubles` + `recalc_face_normals`; non-manifold edges == 0.
2. Voxel remesh if any boolean/text/metaball was involved.
3. Re-seat on Z=0, centre XY; apply all transforms.
4. `bbox` equals the spec; volume plausible (compare to bbox volume x 0.2-0.7 for organic forms).
5. Flat base: organic shapes need a flat bed face. Cut with a plane boolean (`EXACT`) at z=0 or add a base disc. Without it you get a tiny contact patch (a helmet print died on this) — `forge verify` reports bed contact.
6. Overhang check: `forge verify` support %; rotate for fewer supports, or accept slicer auto-support.
7. Hollowing is NOT needed for printing: the slicer handles infill. (The "needs hollowing" remark in VfdEz-My_D0 was about a cavity that must exist for a function, not for printing.)

## Fallbacks, in order, when the result is not good after 6 iterations
1. Find the best existing design on a model site. 2. Remix a found STL with recipe G. 3. Image-to-3D from a free site, then recipes B/C/F to clean it (get the user's OK for any signup/payment; never spend). 4. Tell the user plainly it is beyond reliable capability and why.
