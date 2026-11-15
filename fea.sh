#!/bin/sh
# Run a command inside the FEA container: ./fea.sh python3 solve.py ...
# No network, only this folder mounted.
set -e
cd "$(dirname "$0")"
docker build -q -t finite-stress-analysis . >/dev/null
exec docker run --rm --network none -e OMP_NUM_THREADS=8 -e CCX_NPROC_EQUATION_SOLVER -e FINE_XMAX -e CASES -e STRAIGHT_TETS -v "$PWD":/work finite-stress-analysis "$@"
