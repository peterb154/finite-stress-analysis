# CLAUDE.md

## Layout

- `fea.py`: mesh (gmsh) → write CalculiX `.inp` → run `ccx` → read `.frd` → `summary.json`, `results.vtu`, PNGs.
- `render.py`: zoomed multi-view heat maps from a run's `results.vtu`.
- `fea.sh`: builds the Docker image and runs a command in it (`--network none`, repo mounted at `/work`).
- `cad/`: example inputs (monitor mount v5 = failed design, v8c = fixed design). Keep them as regression checks.
- `examples/monitor-mount/`: the Fusion 360 build script for v8c.

## Units and frame

mm, N, MPa. Example parts use x = depth, y = width, z = up.

## Rules

- Python deps: uv only. Edit `pyproject.toml`, then `uv lock --exclude-newer <2 days ago>`. gmsh's Python module comes from apt inside Docker (no linux-aarch64 wheel on PyPI).
- Always run CalculiX with `CCX_NPROC_EQUATION_SOLVER=1`. Multithreaded spooles gives wrong answers.
- Run a coarse mesh first (`fea.py <name> 6 4`, about 10 s) before a fine one (`5 1.5`, minutes).
- Sanity check after changing solver code: `v5` tilt-pull peak should stay around 54 MPa and `v8c` push-down around 12.5 MPa (fine mesh).
- Peak stresses next to boundary conditions and sharp corners are partly artefacts. Look at the heat map, not just the number.
- `runs/` is gitignored (large). Copy any image worth keeping into `docs/`.
