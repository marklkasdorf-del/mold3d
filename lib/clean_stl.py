"""clean_stl: light mesh hygiene after a build (merge vertices, drop degenerate/duplicate faces, fix winding).
`forge run` calls clean(stl) before verify. Never changes geometry beyond numerical noise."""
import sys


def clean(path):
    import trimesh
    m = trimesh.load(path, force="mesh")
    before = len(m.faces)
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.update_faces(m.unique_faces())
    m.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(m)
    m.export(path)
    return before, len(m.faces)


if __name__ == "__main__":
    print(clean(sys.argv[1]))
