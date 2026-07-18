#!/usr/bin/env bash
# Build _core_compute.cpython-311-darwin.so on macOS, working around
# the lld 22.1.8 LINKEDIT mis-alignment bug (see docs/CONTRIBUTING.md).
#
# Usage:
#   PYTHON=python3.11 ./scripts/build_macos.sh
#
# Required:
#   - Rust stable toolchain (1.78+; we use stable = 1.97.x)
#   - Homebrew lld 22+ (brew install lld)
#   - Python 3.11
#
# What this script does (each step is a workaround for a known issue):
#   1. Set PYO3_PYTHON to a Python 3.11 venv (PyO3 0.22 only supports ≤3.13)
#   2. Run `maturin develop --release` to produce a .so
#   3. Run fix_linkedit_alignment.py to pad LC_SYMTAB.stroff to 8-byte boundary
#      (lld 22.1.8 produces 4-byte-aligned stroff which dyld on macOS 15+
#       rejects with "mis-aligned LINKEDIT string pool")
#   4. Re-codesign the patched .so (the byte insertion invalidates the
#      ad-hoc signature that maturin/cargo put there)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
RUST_DIR="$(cd "$HERE/.." && pwd)"

# Step 1: prepare a Python 3.11 venv if PYO3_PYTHON isn't already a venv
PYTHON_BIN="${PYTHON:-python3.11}"
VENV_DIR="${VENV_DIR:-/tmp/venv311}"

if [ ! -d "$VENV_DIR" ]; then
    echo "[build] creating Python 3.11 venv at $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# Make cargo / rustc reachable (rustup-managed toolchains aren't always on PATH)
TOOLCHAIN_BIN="${HOME}/.rustup/toolchains/stable-aarch64-apple-darwin/bin"
if [ -d "$TOOLCHAIN_BIN" ]; then
    export PATH="$TOOLCHAIN_BIN:$PATH"
fi
export PYO3_PYTHON="$VENV_DIR/bin/python"
export VIRTUAL_ENV="$VENV_DIR"

cd "$RUST_DIR/crates/bindings"

# Step 2: maturin build
echo "[build] maturin develop --release"
maturin develop --release

# Step 3: patch the LINKEDIT alignment
SO_PATH="$(python3 -c "import sys; print(sys.path[0] + '/_core_compute/_core_compute.cpython-311-darwin.so')" 2>/dev/null || true)"
if [ -z "$SO_PATH" ] || [ ! -f "$SO_PATH" ]; then
    SO_PATH="$VENV_DIR/lib/python3.11/site-packages/_core_compute/_core_compute.cpython-311-darwin.so"
fi
echo "[build] patching LINKEDIT alignment: $SO_PATH"
python3 "$HERE/fix_linkedit_alignment.py" "$SO_PATH"

# Step 4: re-sign
echo "[build] re-codesigning $SO_PATH"
codesign --remove-signature "$SO_PATH" 2>/dev/null || true
codesign --force --sign - "$SO_PATH"

# Smoke test
echo "[build] smoke test"
"$VENV_DIR/bin/python" -c "import _core_compute; print('OK:', _core_compute.rust_smoke())"

echo "[build] done."
