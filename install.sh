#!/usr/bin/env bash
# Mold3D one-command installer (macOS + Linux, no sudo).
#   curl -fsSL https://raw.githubusercontent.com/marklkasdorf-del/mold3d/main/install.sh | bash
# Env: MOLD3D_DIR (default ~/.claude/skills/mold3d)  MOLD3D_REPO  MOLD3D_REF (branch)
#      MOLD3D_PRINTER=<profile basename, e.g. prusa-mk4>  MOLD3D_NO_CODEX=1 (skip ~/.codex link)
#      MOLD3D_NO_AUTO_UV=1 (never auto-install uv; fail with manual instructions instead)
set -euo pipefail

REPO="${MOLD3D_REPO:-https://github.com/marklkasdorf-del/mold3d}"
REF="${MOLD3D_REF:-}"
DIR="${MOLD3D_DIR:-$HOME/.claude/skills/mold3d}"

if [ -t 1 ]; then G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; B=$'\033[1m'; N=$'\033[0m'; else G=; Y=; R=; B=; N=; fi
say()  { printf '%s\n' "$*"; }
ok()   { printf '%s✓%s %s\n' "$G" "$N" "$*"; }
warn() { printf '%s!%s %s\n' "$Y" "$N" "$*" >&2; }
die()  { printf '%sx%s %s\n' "$R" "$N" "$*" >&2; exit 1; }
step() { printf '\n%s%s%s\n' "$B" "$*" "$N"; }

command -v git >/dev/null || die "git is required (macOS: xcode-select --install, Debian/Ubuntu: sudo apt install git)."

# 1. Get the code (clone, or fast-forward an existing clone)
step "1/5 Getting Mold3D into $DIR"
if [ -d "$DIR/.git" ]; then
  keep=""
  if [ -f "$DIR/knowledge/printer.json" ]; then   # older clones tracked this file; keep the user's copy
    keep="$(mktemp "${TMPDIR:-/tmp}/mold3d-printer.XXXXXX")"; cp "$DIR/knowledge/printer.json" "$keep"
    git -C "$DIR" checkout -q -- knowledge/printer.json 2>/dev/null || true
  fi
  git -C "$DIR" fetch -q origin ${REF:+"$REF"}
  git -C "$DIR" merge -q --ff-only ${REF:+FETCH_HEAD} ${REF:-@{u}} 2>/dev/null \
    || warn "could not fast-forward (local changes?); keeping the current checkout"
  if [ -n "$keep" ]; then [ -f "$DIR/knowledge/printer.json" ] || cp "$keep" "$DIR/knowledge/printer.json"; rm -f "$keep"; fi
  ok "updated existing install"
elif [ -e "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ]; then
  die "$DIR exists and is not a Mold3D git clone. Set MOLD3D_DIR to somewhere else."
else
  mkdir -p "$(dirname "$DIR")"
  git clone -q ${REF:+--branch "$REF"} "$REPO" "$DIR"
  ok "cloned"
fi
cd "$DIR"

# 2. Codex link
if [ -z "${MOLD3D_NO_CODEX:-}" ] && [ -d "$HOME/.codex" ]; then
  CL="$HOME/.codex/skills/mold3d"
  mkdir -p "$HOME/.codex/skills"
  if [ -L "$CL" ]; then ln -sfn "$DIR" "$CL"; ok "Codex: linked $CL"
  elif [ -e "$CL" ]; then warn "Codex: $CL exists and is not a symlink; left alone"
  else ln -s "$DIR" "$CL"; ok "Codex: linked $CL"; fi
fi

# 3. Python environment
step "2/5 Python environment (.venv-cad)"
PY=".venv-cad/bin/python"
if [ -x "$PY" ] && "$PY" -c 'import build123d, trimesh, manifold3d' 2>/dev/null; then
  ok "already installed (re-run with: rm -rf $DIR/.venv-cad to rebuild)"
else
  # Resolve a Python toolchain: uv (PATH or user-level dirs) > python3.10-3.12 > auto-install uv.
  UV=""
  if command -v uv >/dev/null; then UV="uv"
  else
    for c in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
      [ -x "$c" ] && { UV="$c"; break; }
    done
  fi
  BASEPY=""
  if [ -z "$UV" ]; then
    for c in python3.12 python3.11 python3.10; do
      command -v "$c" >/dev/null && { BASEPY="$c"; break; }
    done
  fi
  if [ -z "$UV" ] && [ -z "$BASEPY" ]; then
    if [ -n "${MOLD3D_NO_AUTO_UV:-}" ]; then
      die "Need Python 3.10-3.12 or uv. Easiest fix (no sudo): curl -LsSf https://astral.sh/uv/install.sh | sh   then re-run this installer."
    fi
    say "Installing uv (Python tool manager, user-level, no password)..."
    command -v curl >/dev/null || die "curl is required to install uv. Install uv or Python 3.12 yourself, then re-run (see https://docs.astral.sh/uv/)."
    # UV_NO_MODIFY_PATH=1 keeps uv from editing your shell profiles; we call it by absolute path.
    if ! curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh; then
      die "Could not install uv (network blocked or astral.sh unreachable?). Check your connection/proxy and re-run, or install Python 3.12 yourself, or see https://docs.astral.sh/uv/getting-started/installation/"
    fi
    for c in "${XDG_BIN_HOME:+$XDG_BIN_HOME/uv}" "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
      [ -n "$c" ] && [ -x "$c" ] && { UV="$c"; break; }
    done
    [ -n "$UV" ] || die "uv installed but not found at ~/.local/bin/uv. Open a new terminal and re-run this installer."
    ok "uv installed ($UV)"
  fi
  if [ -n "$UV" ]; then
    # uv fetches a managed Python 3.12 if none is present; force downloads on even if the user disabled them.
    UV_PYTHON_DOWNLOADS=automatic "$UV" venv -q --allow-existing --python 3.12 .venv-cad
    UV_PYTHON_DOWNLOADS=automatic "$UV" pip install -q --python "$PY" -r requirements-cad.txt
  else
    "$BASEPY" -m venv .venv-cad
    "$PY" -m pip install -q --upgrade pip
    "$PY" -m pip install -q -r requirements-cad.txt
  fi
  ok "CAD packages installed"
fi
if ! "$PY" -c 'import sdf' 2>/dev/null; then
  if [ -n "${UV:-}" ]; then "$UV" pip install -q --python "$PY" git+https://github.com/fogleman/sdf.git
  else "$PY" -m pip install -q git+https://github.com/fogleman/sdf.git; fi \
    && ok "SDF organic lane installed" \
    || warn "SDF lane failed to install (organic shapes disabled; everything else works)"
fi

# 4. Printer profile
step "3/5 Printer profile"
if [ -f knowledge/printer.json ]; then
  ok "keeping existing knowledge/printer.json ($("$PY" -c 'import json;print(json.load(open("knowledge/printer.json"))["name"])' 2>/dev/null || echo custom))"
else
  chosen="${MOLD3D_PRINTER:-}"
  if [ -z "$chosen" ] && { : </dev/tty; } 2>/dev/null; then
    names=(); files=()
    for f in knowledge/printers/*.json; do
      files+=("$f"); names+=("$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["name"])' "$f")")
    done
    say "Which printer do you have?"
    for i in "${!files[@]}"; do printf '  %d) %s\n' $((i+1)) "${names[$i]}"; done
    printf '  %d) generic 220x220 (anything else; edit knowledge/printer.json later)\n' $(( ${#files[@]}+1 ))
    printf 'Number [%d]: ' $(( ${#files[@]}+1 ))
    read -r n </dev/tty || n=""
    if [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -ge 1 ] && [ "$n" -le "${#files[@]}" ]; then chosen="$(basename "${files[$((n-1))]}" .json)"; fi
  fi
  if [ -n "$chosen" ] && [ -f "knowledge/printers/$chosen.json" ]; then
    cp "knowledge/printers/$chosen.json" knowledge/printer.json; ok "printer: $chosen"
  else
    [ -z "$chosen" ] || warn "no profile named '$chosen' in knowledge/printers/; using generic"
    printf '%s\n' '{"name": "generic 220 FDM (edit me)", "bed": [220, 220, 250], "nozzle": 0.4, "layer": 0.2, "material": "PLA", "slicer_cmd": "", "support_angle": 30, "support_trap_gap": 2.0}' > knowledge/printer.json
    ok "printer: generic 220 x 220 x 250"
  fi
fi

# 5. Optional tools
step "4/5 Optional tools (not installed for you)"
opt() { if command -v "$1" >/dev/null 2>&1 || { [ -n "${3:-}" ] && [ -e "$3" ]; }; then ok "$1 found: $2"; else say "  - $1 missing: $2"; fi; }
opt blender "photo-real renders and showcase videos" /Applications/Blender.app
opt openscad "the OpenSCAD design lane"
opt ffmpeg "showcase video / GIF output"

# 6. Verify
step "5/5 Checking it works"
# Doctor is advisory: show required-dependency problems only, summarise optional extras, never abort here.
DOC="$("$DIR/bin/forge" doctor 2>&1 || true)"
printf '%s\n' "$DOC" | grep -A1 '\[MISSING\]' || true
NOPT="$(printf '%s\n' "$DOC" | grep -c '\[optional\]' || true)"
[ "${NOPT:-0}" -gt 0 ] && say "  ($NOPT optional extras not installed; see: $DIR/bin/forge doctor)"
SMOKE="$(mktemp -d "${TMPDIR:-/tmp}/mold3d.XXXXXX")"
trap 'rm -rf "$SMOKE"' EXIT
if "$DIR/bin/forge" mech build fitcard --out "$SMOKE/fitcard" >"$SMOKE/log" 2>&1; then
  ok "smoke test: built and self-tested the Fit Card (all motion sweeps clear)"
else
  tail -8 "$SMOKE/log" >&2; die "smoke test failed (see above). Run: $DIR/bin/forge doctor"
fi

printf '\n%sMold3D installed ✓%s\n\n' "$G$B" "$N"
say "Try it in Claude Code:   /mold3d print-in-place gear fidget, about 50 mm"
say "Check any STL:           $DIR/bin/forge preflight your_part.stl"
say "First print: the Fit Card calibrates your printer in ~1 hour:  $DIR/bin/forge mech build fitcard"
