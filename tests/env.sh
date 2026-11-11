# sourced by the test scripts: picks the CAD interpreter (FORGE_CAD_PY, else <skill>/.venv-cad, else python3)
F="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAD="${FORGE_CAD_PY:-}"
[ -n "$CAD" ] || { [ -x "$F/.venv-cad/bin/python" ] && CAD="$F/.venv-cad/bin/python" || CAD="$(command -v python3)"; }
export FORGE_CAD_PY="$CAD"
