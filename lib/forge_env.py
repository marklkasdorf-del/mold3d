"""forge_env: where things live. Everything is relative to the skill directory unless an env var says otherwise.

  FORGE_ROOT     skill directory (default: parent of lib/)
  FORGE_CAD_PY   python with build123d + trimesh + manifold3d ...   (default: $FORGE_ROOT/.venv-cad/bin/python, else sys.executable)
  FORGE_AI_PY    python with torch + diffusers + transformers ...   (default: $FORGE_ROOT/.venv-ai/bin/python, else FORGE_CAD_PY)
  MOLD3D_OUT     where designs are written (FORGE_OUT also works)    (default: ./mold3d in the directory you run forge from)
  FORGE_PRINTER  path to a printer profile json                     (default: knowledge/printer.json)
  BLENDER        Blender binary (default: auto-detect)
  OPENSCAD       OpenSCAD binary (default: auto-detect)
"""
import os, sys, shutil

LIB = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("FORGE_ROOT") or os.path.dirname(LIB)
OUT = os.path.abspath(os.environ.get("MOLD3D_OUT") or os.environ.get("FORGE_OUT") or os.path.join(os.getcwd(), "mold3d"))


def _venv_py(name):
    p = os.path.join(ROOT, name, "bin", "python")
    if not os.path.exists(p):
        p = os.path.join(ROOT, name, "Scripts", "python.exe")
    return p if os.path.exists(p) else None


CAD_PY = os.environ.get("FORGE_CAD_PY") or _venv_py(".venv-cad") or sys.executable
AI_PY = os.environ.get("FORGE_AI_PY") or _venv_py(".venv-ai") or CAD_PY


def find_blender():
    if os.environ.get("BLENDER", "").lower() in ("none", "off", "0"):
        return None   # explicit opt-out (also used to test the no-Blender path)
    for c in (os.environ.get("BLENDER"), shutil.which("blender"),
              "/Applications/Blender.app/Contents/MacOS/Blender", "/usr/bin/blender",
              "C:/Program Files/Blender Foundation/Blender/blender.exe"):
        if c and os.path.exists(c):
            return c
    return None


def find_openscad():
    for c in (os.environ.get("OPENSCAD"), shutil.which("openscad"), "/opt/homebrew/bin/openscad",
              "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"):
        if c and os.path.exists(c):
            return c
    return None
