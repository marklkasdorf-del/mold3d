#!/usr/bin/env python3
"""ar.py: see a print in your room at REAL size before printing. venv: .venv-cad (usd-core)

    forge ar model.stl [--color grey|white|black|red|blue|green|orange|yellow|purple|pink] [--parts DIR] [--out X]
      -> X.usdz  (iPhone / iPad / Vision Pro: tap it -> AR Quick Look -> "place on desk", 1:1 scale)
      -> X.glb   (Quest 3S browser / any web viewer / Blender)
--parts DIR: a MechKit/flexify parts folder -> each part its own mesh + colour (moving parts pop).
Units: STL is mm, ARKit wants metres + Y-up -> converted here (that's what makes the scale real).
"""
import argparse, glob, os, sys
import numpy as np
import trimesh

COLORS = {"grey": (0.55, 0.57, 0.60), "white": (0.92, 0.91, 0.88), "black": (0.08, 0.08, 0.09),
          "red": (0.80, 0.12, 0.10), "blue": (0.10, 0.30, 0.80), "green": (0.15, 0.60, 0.25),
          "orange": (0.95, 0.45, 0.08), "yellow": (0.95, 0.80, 0.10), "purple": (0.45, 0.20, 0.70),
          "pink": (0.95, 0.50, 0.70)}
PART_PALETTE = ["grey", "orange", "blue", "green", "purple", "yellow", "red", "pink", "white"]


def _prep(t, max_faces=150000):
    if len(t.faces) > max_faces:
        import fast_simplification
        v, f = fast_simplification.simplify(t.vertices, t.faces, 1 - max_faces / len(t.faces))
        t = trimesh.Trimesh(v, f)
    return t


def write_usdz(meshes, out_usdz, centre):
    from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf, Vt, UsdUtils
    usdc = out_usdz[:-5] + "_tmp.usdc"
    stage = Usd.Stage.CreateNew(usdc)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, "/Model")
    stage.SetDefaultPrim(root.GetPrim())
    for i, (name, t, rgb) in enumerate(meshes):
        v = (t.vertices - centre) * 0.001                       # mm -> m, centred, sitting on the floor
        v = np.stack([v[:, 0], v[:, 2], -v[:, 1]], 1)            # Z-up -> Y-up
        path = f"/Model/{name}"
        m = UsdGeom.Mesh.Define(stage, path)
        m.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(v.astype(np.float32)))
        m.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(t.faces), 3, np.int32)))
        m.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(t.faces.astype(np.int32).ravel()))
        m.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        m.CreateDoubleSidedAttr(False)
        mat = UsdShade.Material.Define(stage, f"/Model/mat_{name}")
        sh = UsdShade.Shader.Define(stage, f"/Model/mat_{name}/pbr")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
        sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.55)
        sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(m.GetPrim()).Bind(mat)
    stage.GetRootLayer().Save()
    ok = UsdUtils.CreateNewARKitUsdzPackage(Sdf.AssetPath(usdc), out_usdz)
    os.remove(usdc)
    return bool(ok)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model"); ap.add_argument("--color", default="grey"); ap.add_argument("--parts")
    ap.add_argument("--out")
    a = ap.parse_args()
    base = a.out or os.path.splitext(a.model)[0]
    meshes = []
    if a.parts:
        files = sorted(glob.glob(os.path.join(a.parts, "*.stl")))
        for i, f in enumerate(files):
            t = _prep(trimesh.load(f, force="mesh"), max_faces=max(20000, 150000 // max(1, len(files))))
            nm = "".join(c if c.isalnum() else "_" for c in os.path.splitext(os.path.basename(f))[0])
            meshes.append((nm, t, COLORS[PART_PALETTE[i % len(PART_PALETTE)]]))
    else:
        meshes.append(("part", _prep(trimesh.load(a.model, force="mesh")), COLORS.get(a.color, COLORS["grey"])))
    allv = np.concatenate([t.vertices for _, t, _ in meshes])
    centre = np.array([(allv[:, 0].min() + allv[:, 0].max()) / 2, (allv[:, 1].min() + allv[:, 1].max()) / 2, allv[:, 2].min()])
    ok = write_usdz(meshes, base + ".usdz", centre)
    scene = trimesh.Scene()
    for nm, t, rgb in meshes:
        tt = t.copy(); tt.apply_translation(-centre)
        tt.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))   # Z-up -> Y-up (glTF)
        tt.apply_scale(0.001)
        tt.visual = trimesh.visual.ColorVisuals(tt, face_colors=np.tile((np.array(rgb) * 255).astype(np.uint8).tolist() + [255], (len(tt.faces), 1)))
        scene.add_geometry(tt, node_name=nm)
    scene.export(base + ".glb")
    ext = allv.max(0) - allv.min(0)
    print(f"usdz {'ok' if ok else 'FAILED'}: {base}.usdz   glb: {base}.glb   real size {ext[0]:.0f} x {ext[1]:.0f} x {ext[2]:.0f} mm, "
          f"{sum(len(t.faces) for _, t, _ in meshes)} tris, {len(meshes)} part(s)")


if __name__ == "__main__":
    main()
