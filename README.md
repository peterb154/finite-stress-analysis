# finite-stress-analysis

Quick, local FEA for 3D-printed parts: STEP in → stress heat maps out.
gmsh meshes the part, CalculiX solves it, and everything runs in Docker with no network.

Status: extracted from the HP 32s monitor-mount project. It is still hard-coded for
that part's supports and loads (see `examples/monitor-mount/`). Generalizing is the next step.

## Run

```sh
STRAIGHT_TETS=1 CCX_NPROC_EQUATION_SOLVER=1 FINE_XMAX=14 CASES=1,2,5,6 \
  ./fea.sh python3 -u fea.py v8c 5 1.5        # name, coarse mesh mm, fine mesh mm
./fea.sh python3 render.py v8c 2_push_down_100N_vm 40   # case_field, colour-scale max (MPa)
```

Inputs: `cad/<name>.step` + `cad/<name>_holes.json`. Outputs: `runs/<name>/` with
`summary.json`, `results.vtu` (open in [ParaView](https://www.paraview.org/)) and PNGs.

## What it reports

- Von Mises stress per load case, plus where the peak is.
- "Layer tension": normal stress along the build direction for three print orientations.
  Layers pulled apart fail far below the in-plane strength.
- Max deflection.

## Gotchas

- **Keep `CCX_NPROC_EQUATION_SOLVER=1`.** Multithreaded spooles in Debian's CalculiX 2.20
  returns wrong stresses.
- ~180k nodes fits in a ~12 GB Docker VM; ~300k does not.
- `STRAIGHT_TETS=1` avoids inverted curved tet10s on some geometry.

## Limits

- Isotropic PETG (E = 2 GPa); layer weakness is checked afterwards, not modelled.
- Linear static only: no creep, impact or snap-fits.
- Not calibrated against a physical break test. Use the results to compare designs.
