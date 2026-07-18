#!/usr/bin/env bash
# Build _core_compute on Linux (e.g. inside rust/Dockerfile.test).
#
# Linux does NOT have the Mach-O LINKEDIT mis-alignment bug (that's a
# macOS dyld check on the LC_SYMTAB.stroff of cdylibs). On Linux the
# .so is an ELF and is unaffected.
#
# Usage (inside the container):
#   bash /src/rust/scripts/build-linux.sh
#
# Usage (host with docker installed):
#   docker build -f rust/Dockerfile.test -t zt-rust-builder .
#   docker run --rm -v "$(pwd):/src" zt-rust-builder \
#       bash /src/rust/scripts/build-linux.sh
#
# Output: a CPython 3.11 wheel at /src/dist/*.whl (suitable for `pip install`).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
RUST_DIR="$(cd "$HERE/.." && pwd)"

# Ensure pip / maturin are fresh in the container's Python.
python3 -m pip install --upgrade pip maturin 1>&2

cd "$RUST_DIR/crates/bindings"

# Build a wheel (do NOT `develop` — that would try to install into the
# container's site-packages, which gets thrown away with the container).
maturin build --release --interpreter python3.11

# Collect wheels into /src/dist/ for easy copy-out.
mkdir -p /src/dist
cp target/wheels/*.whl /src/dist/ 2>/dev/null || \
    find /tmp -name "*.whl" -path "*cp311*" -exec cp {} /src/dist/ \;

ls -la /src/dist/

# Smoke test inside the container (cpython will load the just-built
# extension from the wheel before the container exits).
pip install --force-reinstall /src/dist/*.whl
python3 -c "import _core_compute; print('OK:', _core_compute.rust_smoke())"
