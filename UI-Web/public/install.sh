#!/bin/sh
# footprint installer — no npm, no git. Needs python3.
#   curl -fsSL https://www.tracefootprint.space/install.sh | sh -s -- fp_yourkey
# Re-run any time to update. Keeps your data/, adapters/ and .venv/.
set -eu

APP="$HOME/.footprint/app"
BIN="$HOME/.local/bin"
SRC="https://github.com/Amanlabh/footprint/tarball/main"

command -v python3 >/dev/null 2>&1 || {
  echo "footprint needs python3. macOS: xcode-select --install · Linux: install python3, then re-run."
  exit 1
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
echo "downloading footprint…"
curl -fsSL "$SRC" | tar -xz -C "$tmp" --strip-components=1

mkdir -p "$APP" "$BIN"
rm -rf "$APP/footprint_core" "$APP/skills" # fresh code; data/ adapters/ .venv/ untouched
cp -R "$tmp/footprint.py" "$tmp/footprint_core" "$tmp/skills" "$APP/"

cat >"$BIN/footprint" <<'EOF'
#!/bin/sh
APP="$HOME/.footprint/app"
PY="$APP/.venv/bin/python"
case "${1:-}" in
  train|eval|serve|install)  # local model mode: one-time venv + backend
    [ -x "$PY" ] || python3 "$APP/footprint.py" setup || exit 1 ;;
esac
[ -x "$PY" ] || PY=python3
[ $# -gt 0 ] || set -- status
exec "$PY" "$APP/footprint.py" "$@"
EOF
chmod +x "$BIN/footprint"

case ":$PATH:" in
  *":$BIN:"*) ;;
  *)
    case "${SHELL:-}" in
      */zsh) rc="$HOME/.zshrc" ;;
      */bash) [ "$(uname)" = Darwin ] && rc="$HOME/.bash_profile" || rc="$HOME/.bashrc" ;;
      *) rc="$HOME/.profile" ;;
    esac
    grep -qs '.local/bin' "$rc" || echo 'export PATH="$HOME/.local/bin:$PATH"' >>"$rc"
    echo "~/.local/bin is in $rc — open a new terminal to use 'footprint'"
    ;;
esac

if [ $# -gt 0 ]; then
  "$BIN/footprint" login "$1"
else
  "$BIN/footprint" context install
  echo "installed. sign in: footprint login fp_yourkey (key from https://www.tracefootprint.space/account)"
fi
