#!/usr/bin/env bash
# Mold3D one-command installer (macOS + Linux, no sudo).
#   curl -fsSL https://raw.githubusercontent.com/marklkasdorf-del/mold3d/main/install.sh | bash
# Env: MOLD3D_DIR (default ~/.claude/skills/mold3d)  MOLD3D_REPO  MOLD3D_REF (branch)
#      MOLD3D_PRINTER=<profile basename, e.g. prusa-mk4>  MOLD3D_NO_CODEX=1 (skip ~/.codex link)
#      MOLD3D_NO_AUTO_UV=1 (never auto-install uv; fail with manual instructions instead)
#      MOLD3D_VERBOSE=1 (show every technical detail; default output is short and plain)
# Raw command output goes to $MOLD3D_DIR/install.log (overwritten each run) and is pointed to on failure.
set -euo pipefail

REPO="${MOLD3D_REPO:-https://github.com/marklkasdorf-del/mold3d}"
REF="${MOLD3D_REF:-}"
DIR="${MOLD3D_DIR:-$HOME/.claude/skills/mold3d}"
VERBOSE="${MOLD3D_VERBOSE:-}"

TTY=0; [ -t 1 ] && TTY=1
if [ "$TTY" = 1 ]; then G=$'\033[32m'; R=$'\033[31m'; B=$'\033[1m'; D=$'\033[2m'; N=$'\033[0m'; else G=; R=; B=; D=; N=; fi
OPEN=0      # 1 while a step line is waiting for its result mark
CHILD=""
UPGRADE=0; [ -d "$DIR/.git" ] && UPGRADE=1

# Log: starts in a temp file (the install folder may not exist yet), moves into $DIR once it does.
if [ "$UPGRADE" = 1 ]; then LOG="$DIR/install.log"; : >"$LOG"; else LOG="$(mktemp "${TMPDIR:-/tmp}/mold3d-log.XXXXXX")"; fi
MSGF="$(mktemp "${TMPDIR:-/tmp}/mold3d-msg.XXXXXX")"   # worker -> main: line 1 = plain error, line 2 = what to do
SMOKE=""
cleanup() { [ -n "$CHILD" ] && kill "$CHILD" 2>/dev/null || true; rm -f "$MSGF"; [ -n "$SMOKE" ] && rm -rf "$SMOKE"; return 0; }
trap cleanup EXIT
trap 'cleanup; [ "$OPEN" = 1 ] && printf "\n"; exit 130' INT TERM

setmsg() { printf '%s\n%s\n' "$1" "${2:-}" >"$MSGF"; }
end_line() { [ "$OPEN" = 1 ] && printf '\n'; OPEN=0; return 0; }
# Plain failure: one sentence, what to do, where the details are.
fail() {   # $1 default sentence, $2 default advice (the worker's own message wins)
  [ "$OPEN" = 1 ] && printf '%s✗%s\n' "$R" "$N"; OPEN=0
  local a b; a="$(sed -n 1p "$MSGF" 2>/dev/null || true)"; b="$(sed -n 2p "$MSGF" 2>/dev/null || true)"
  printf '\n%s✗%s %s\n' "$R" "$N" "${a:-$1}" >&2
  [ -n "${b:-$2}" ] && printf '  %s\n' "${b:-$2}" >&2
  printf '  Details: %s\n\n' "$LOG" >&2
  exit 1
}
label() { printf '%-44s' "$1"; OPEN=1; }
mark()  { printf '%s✓%s' "$G" "$N"; }

# run_step "label" worker-fn [fn args]: runs the worker with a spinner; its output goes to the log (or the screen when verbose).
run_step() {
  local lbl="$1"; shift; : >"$MSGF"
  label "$lbl"
  if [ -n "$VERBOSE" ]; then
    printf '\n'; OPEN=0
    if ( "$@" ) 2>&1 | tee -a "$LOG"; then printf '%s\n' "  $(mark)"; return 0; else return 1; fi
  fi
  ( "$@" ) >>"$LOG" 2>&1 &
  CHILD=$!
  if [ "$TTY" = 1 ]; then
    local i=0 frames='|/-\'
    while kill -0 "$CHILD" 2>/dev/null; do printf '%s\b' "${frames:$((i % 4)):1}"; i=$((i + 1)); sleep 0.15; done
  fi
  local rc=0; wait "$CHILD" || rc=$?
  CHILD=""
  if [ "$rc" = 0 ]; then mark; printf '\n'; OPEN=0; return 0; fi
  return 1
}

# ---- workers: run in a subshell, explicit error handling, chatty output is fine (it goes to the log) ----

do_download() {
  set +e
  if [ -d "$DIR/.git" ]; then
    local keep=""
    if [ -f "$DIR/knowledge/printer.json" ]; then   # older clones tracked this file; keep the user's copy
      keep="$(mktemp "${TMPDIR:-/tmp}/mold3d-printer.XXXXXX")"; cp "$DIR/knowledge/printer.json" "$keep"
      git -C "$DIR" checkout -q -- knowledge/printer.json 2>/dev/null
    fi
    if ! git -C "$DIR" fetch -q origin ${REF:+"$REF"}; then
      setmsg "Couldn't download the latest Mold3D." "Check your internet connection, then run the same command again."; return 1
    fi
    git -C "$DIR" merge -q --ff-only ${REF:+FETCH_HEAD} ${REF:-@{u}} 2>/dev/null \
      || echo "could not fast-forward (local changes?); keeping the current checkout"
    if [ -n "$keep" ]; then [ -f "$DIR/knowledge/printer.json" ] || cp "$keep" "$DIR/knowledge/printer.json"; rm -f "$keep"; fi
    echo "updated existing install"
  elif [ -e "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ]; then
    setmsg "The folder $DIR already exists and isn't Mold3D." "Move that folder away (or set MOLD3D_DIR to another place) and run the command again."; return 1
  else
    mkdir -p "$(dirname "$DIR")"
    if ! git clone -q ${REF:+--branch "$REF"} "$REPO" "$DIR"; then
      case "$REPO" in
        http*|git@*|ssh:*) setmsg "Couldn't download Mold3D." "Check your internet connection, then run the same command again." ;;
        *) setmsg "Couldn't find Mold3D at $REPO." "Check that location and run the command again." ;;
      esac
      return 1
    fi
    echo "cloned"
  fi
  return 0
}

do_setup() {
  set +e
  cd "$DIR" || return 1
  # Codex link
  if [ -z "${MOLD3D_NO_CODEX:-}" ] && [ -d "$HOME/.codex" ]; then
    local CL="$HOME/.codex/skills/mold3d"
    mkdir -p "$HOME/.codex/skills"
    if [ -L "$CL" ]; then ln -sfn "$DIR" "$CL"; echo "Codex: linked $CL"
    elif [ -e "$CL" ]; then echo "Codex: $CL exists and is not a symlink; left alone"
    else ln -s "$DIR" "$CL"; echo "Codex: linked $CL"; fi
  fi
  # Python environment
  local netmsg="Check your internet connection, then run the same command again."
  if [ -x "$PY" ] && "$PY" -c 'import build123d, trimesh, manifold3d' 2>/dev/null; then
    echo "CAD packages already installed (rebuild with: rm -rf $DIR/.venv-cad)"
  else
    # Resolve a Python toolchain: uv (PATH or user-level dirs) > python3.10-3.12 > auto-install uv.
    local UV="" BASEPY="" c
    if command -v uv >/dev/null; then UV="uv"
    else
      for c in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        [ -x "$c" ] && { UV="$c"; break; }
      done
    fi
    if [ -z "$UV" ]; then
      for c in python3.12 python3.11 python3.10; do
        command -v "$c" >/dev/null && { BASEPY="$c"; break; }
      done
    fi
    if [ -z "$UV" ] && [ -z "$BASEPY" ]; then
      if [ -n "${MOLD3D_NO_AUTO_UV:-}" ]; then
        setmsg "Mold3D needs Python, and this computer doesn't have a suitable one." "Run:  curl -LsSf https://astral.sh/uv/install.sh | sh   then run the Mold3D command again."; return 1
      fi
      echo "Installing uv (Python tool manager, user-level, no password)..."
      if ! command -v curl >/dev/null; then
        setmsg "Mold3D needs 'curl', which isn't installed." "Install curl (or Python 3.12), then run the command again."; return 1
      fi
      # UV_NO_MODIFY_PATH=1 keeps uv from editing your shell profiles; we call it by absolute path.
      if ! curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh; then
        setmsg "Couldn't download the tools Mold3D needs." "$netmsg"; return 1
      fi
      for c in "${XDG_BIN_HOME:+$XDG_BIN_HOME/uv}" "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        [ -n "$c" ] && [ -x "$c" ] && { UV="$c"; break; }
      done
      if [ -z "$UV" ]; then setmsg "The setup tools were installed but couldn't be found." "Open a new terminal tab and run the Mold3D command again."; return 1; fi
      echo "uv installed ($UV)"
    fi
    if [ -n "$UV" ]; then
      # uv fetches a managed Python 3.12 if none is present; force downloads on even if the user disabled them.
      UV_PYTHON_DOWNLOADS=automatic "$UV" venv -q --allow-existing --python 3.12 .venv-cad \
        && UV_PYTHON_DOWNLOADS=automatic "$UV" pip install -q --python "$PY" -r requirements-cad.txt \
        || { setmsg "Couldn't finish setting up Mold3D's tools." "$netmsg"; return 1; }
    else
      { "$BASEPY" -m venv .venv-cad && "$PY" -m pip install -q --upgrade pip && "$PY" -m pip install -q -r requirements-cad.txt; } \
        || { setmsg "Couldn't finish setting up Mold3D's tools." "$netmsg"; return 1; }
    fi
    echo "CAD packages installed"
    SDFUV="$UV"
  fi
  if ! "$PY" -c 'import sdf' 2>/dev/null; then
    local U="${SDFUV:-}"
    if [ -z "$U" ]; then if command -v uv >/dev/null; then U=uv; elif [ -x "$HOME/.local/bin/uv" ]; then U="$HOME/.local/bin/uv"; fi; fi
    if [ -n "$U" ]; then "$U" pip install -q --python "$PY" git+https://github.com/fogleman/sdf.git
    else "$PY" -m pip install -q git+https://github.com/fogleman/sdf.git; fi \
      && echo "SDF organic lane installed" \
      || echo "SDF lane failed to install (organic shapes disabled; everything else works)"
  fi
  # Optional tools (never installed for you)
  opt() { if command -v "$1" >/dev/null 2>&1 || { [ -n "${3:-}" ] && [ -e "$3" ]; }; then echo "$1 found: $2"; else echo "  - $1 missing (optional): $2"; fi; }
  opt blender "photo-real renders and showcase videos" /Applications/Blender.app
  opt openscad "the OpenSCAD design lane"
  opt ffmpeg "showcase video / GIF output"
  return 0
}

do_test() {
  set +e
  cd "$DIR" || return 1
  # Doctor is advisory: record required-dependency problems, summarise optional extras, never abort here.
  local DOC NOPT
  DOC="$("$DIR/bin/forge" doctor 2>&1)"
  printf '%s\n' "$DOC" | grep -A1 '\[MISSING\]'
  NOPT="$(printf '%s\n' "$DOC" | grep -c '\[optional\]')"
  [ "${NOPT:-0}" -gt 0 ] && echo "($NOPT optional extras not installed; see: $DIR/bin/forge doctor)"
  if "$DIR/bin/forge" mech build fitcard --out "$SMOKE/fitcard" >"$SMOKE/log" 2>&1; then
    echo "smoke test: built and self-tested the Fit Card (all motion sweeps clear)"
    return 0
  fi
  tail -20 "$SMOKE/log"
  setmsg "The final check didn't pass." "Run the same command again; if it still fails, send the Details file below to whoever gave you Mold3D."
  return 1
}

# ---- main ----

WILL_ASK=1
{ [ -n "${MOLD3D_PRINTER:-}" ] || [ -f "$DIR/knowledge/printer.json" ]; } && WILL_ASK=0
{ : </dev/tty; } 2>/dev/null || WILL_ASK=0

printf '%sMold3D installer%s\n' "$B" "$N"
if [ "$UPGRADE" = 1 ]; then printf 'Updating Mold3D. This takes about a minute.\n\n'
elif [ "$WILL_ASK" = 1 ]; then printf "This takes about 2-3 minutes. You'll be asked one question.\n\n"
else printf 'This takes about 2-3 minutes.\n\n'; fi

if ! command -v git >/dev/null; then
  setmsg "Mold3D needs 'git', which isn't installed on this computer yet." "Mac: type  xcode-select --install  and press Enter. Linux: sudo apt install git. Then run this again."
  fail "git is missing."
fi

# [1/4] download
if [ "$UPGRADE" = 1 ]; then L1="[1/4] Updating Mold3D..."; else L1="[1/4] Downloading Mold3D..."; fi
run_step "$L1" do_download || fail "Couldn't download Mold3D." "Check your internet connection, then run the same command again."
if [ "$LOG" != "$DIR/install.log" ]; then   # the folder exists now: move the log in
  cat "$LOG" >"$DIR/install.log"; rm -f "$LOG"; LOG="$DIR/install.log"
fi
cd "$DIR"
PY=".venv-cad/bin/python"

# [2/4] setup
if [ -x "$PY" ] && "$PY" -c 'import build123d, trimesh, manifold3d' 2>/dev/null; then L2="[2/4] Checking your setup..."
else L2="[2/4] Setting up (the slow part, ~2 min)..."; fi
run_step "$L2" do_setup || fail "Setup didn't finish." "Check your internet connection, then run the same command again."

# [3/4] printer
if [ -f knowledge/printer.json ]; then
  pname="$("$PY" -c 'import json;print(json.load(open("knowledge/printer.json"))["name"])' 2>/dev/null | sed -E 's/ *\((example|sample|demo)\)//' || echo custom)"
  label "[3/4] Your 3D printer..."; mark; printf ' printer: %s\n' "$pname"; OPEN=0
else
  chosen="${MOLD3D_PRINTER:-}"
  files=(); names=()
  while IFS=$'\t' read -r b s; do
    [ -n "$b" ] && { files+=("$b"); names+=("$s"); }
  done <<EOP
$("$PY" - <<'PYEOF'
import glob, json, os, re
for f in sorted(glob.glob("knowledge/printers/*.json")):
    n = json.load(open(f))["name"]
    n = re.sub(r"\s*\((example|sample|demo)\)", "", n, flags=re.I)   # "(example)" etc.
    n = re.sub(r"\s*\([^)]*\bmm\b[^)]*\)", "", n)                    # "(256 mm cube)"
    n = n.replace("-class", "")
    n = re.sub(r"^(.*?) (\S+/\S+)$", r"\1 (\2)", n.strip())          # Bambu Lab X1/P1/A1 -> Bambu Lab (X1/P1/A1)
    print(os.path.basename(f)[:-5] + "\t" + n)
PYEOF
)
EOP
  nf=${#files[@]}; shown=""
  if [ -z "$chosen" ] && [ "$WILL_ASK" = 1 ]; then
    printf '[3/4] Which 3D printer do you have?\n'
    line="  "; i=0
    while [ "$i" -lt "$nf" ]; do
      item="$((i + 1))) ${names[$i]}"
      if [ ${#line} -gt 2 ] && [ $(( ${#line} + ${#item} + 3 )) -gt 80 ]; then printf '%s\n' "$line"; line="  "; fi
      [ ${#line} -gt 2 ] && line="$line   "; line="$line$item"; i=$((i + 1))
    done
    item="$((nf + 1))) Something else"
    if [ ${#line} -gt 2 ] && [ $(( ${#line} + ${#item} + 3 )) -gt 80 ]; then printf '%s\n' "$line"; line="  "; fi
    [ ${#line} -gt 2 ] && line="$line   "; printf '%s%s\n' "$line" "$item"
    printf '   Type a number and press Enter: '
    read -r n </dev/tty || n=""
    if [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -ge 1 ] && [ "$n" -le "$nf" ]; then chosen="${files[$((n-1))]}"; shown="${names[$((n-1))]}"; fi
    OPEN=0; pre="   "
  else
    label "[3/4] Your 3D printer..."; pre=""
  fi
  if [ -n "$chosen" ] && [ -f "knowledge/printers/$chosen.json" ]; then
    cp "knowledge/printers/$chosen.json" knowledge/printer.json
    if [ -z "$shown" ]; then
      i=0; while [ "$i" -lt "$nf" ]; do [ "${files[$i]}" = "$chosen" ] && shown="${names[$i]}"; i=$((i + 1)); done
    fi
    printf '%s' "$pre"; mark; printf ' %s\n' "${shown:-$chosen}"; OPEN=0
  else
    [ -z "$chosen" ] || printf '\n  (No printer called "%s" here, so Mold3D will use a generic one.)\n%s' "$chosen" "$pre"
    printf '%s\n' '{"name": "generic 220 FDM (edit me)", "bed": [220, 220, 250], "nozzle": 0.4, "layer": 0.2, "material": "PLA", "slicer_cmd": "", "support_angle": 30, "support_trap_gap": 2.0}' > knowledge/printer.json
    printf '%s' "$pre"; mark; printf ' Something else (generic 220 x 220 mm)\n'; OPEN=0
  fi
fi

# [4/4] test
SMOKE="$(mktemp -d "${TMPDIR:-/tmp}/mold3d.XXXXXX")"
run_step "[4/4] Testing that it works..." do_test || fail "The final check didn't pass." "Run the same command again."

# ---- finish ----
printf '\n%s✅ Done! Mold3D is installed.%s\n\n' "$G$B" "$N"
printf 'Next:\n'
printf '  1. Open a NEW terminal tab  (Mac: press ⌘T)\n'
if command -v claude >/dev/null 2>&1; then
  printf '  2. Type:   claude\n'
  printf '  3. Then type:   /mold3d a phone stand for my iPhone\n'
else
  printf "  2. Don't have Claude Code yet? Get it at https://claude.com/claude-code, then type  claude\n"
  printf '  3. Then type:   /mold3d a phone stand for my iPhone\n'
  if [ -z "${MOLD3D_NO_CODEX:-}" ] && [ -d "$HOME/.codex" ]; then
    printf '\nUsing Codex? Open it and ask for a part — Mold3D is linked there too.\n'
  fi
fi
printf '\nFirst print tip: ask "/mold3d make me a Fit Card" — it tunes Mold3D to your printer.\n'
