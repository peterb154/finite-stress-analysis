# finite-stress-analysis

Quick, local stress analysis (FEA) for 3D-printed parts, built to be driven by
[Claude Code](https://claude.com/claude-code).

STEP file in → stress heat maps and a pass/fail summary out. It answers the question
"will this printed bracket break, and where?" before you spend five hours printing it.

![v5 vs v8c](docs/compare.png)

*The first project: an HP 32s monitor → VESA adapter. v5 (left) cracked twice at the
red junction. v8c (right) carries the same load at about a quarter of the stress.*

## How it works

1. **[gmsh](https://gmsh.info/)** meshes the STEP file into tetrahedra (finer where it matters).
2. **[CalculiX](http://www.calculix.de/)** solves linear static stress for each load case.
3. Python pulls out peak von Mises stress, deflection and **layer tension**: the stress pulling
   print layers apart, checked for each print orientation. Layer adhesion is usually what fails.
4. Heat maps go to PNG on a fixed colour scale, so different versions compare at a glance.
   Full results go to `.vtu` for [ParaView](https://www.paraview.org/).

Everything runs in Docker with `--network none`, so the only thing you install is Docker.

## Quick start

```sh
git clone https://github.com/peterb154/finite-stress-analysis
cd finite-stress-analysis
STRAIGHT_TETS=1 CCX_NPROC_EQUATION_SOLVER=1 CASES=1,2,5,6 \
  ./fea.sh python3 -u fea.py v8c 5 1.5                    # name, coarse mm, fine mm
./fea.sh python3 render.py v8c 2_push_down_100N_vm 40     # case_field, scale max MPa
open runs/v8c/2_push_down_100N_vm.png
```

Inputs are `cad/<name>.step` + `cad/<name>_holes.json`. Outputs go to `runs/<name>/`.

> **Status:** early. The supports and loads are still hard-coded for the monitor-mount
> example. A per-part config, a CLI that runs from any folder and a Claude Code skill are
> planned in [#1](https://github.com/peterb154/finite-stress-analysis/issues/1).

## Using it with Claude Code

The intended loop:

1. Design the part in CAD (Fusion 360 with an MCP server works well, or any STEP export).
2. Ask Claude to check it: it writes the config (material, what's bolted down, where the loads
   go), runs a coarse mesh, then a fine one, and reads `summary.json`.
3. Look at the heat maps, change a parameter, re-run, compare.

## Gotchas

- **Keep `CCX_NPROC_EQUATION_SOLVER=1`.** Multithreaded spooles in Debian's CalculiX 2.20
  returns wrong stresses. Single-threaded is slower but correct.
- About 180k nodes fits in a ~12 GB Docker VM; about 300k does not.
- `STRAIGHT_TETS=1` avoids inverted curved elements on some geometry.

## Limits

- The material is isotropic (PETG, E = 2 GPa). Layer weakness is checked after solving, not modelled.
- Linear static only: no creep, impact, snap-fits or large deflections.
- Not calibrated against physical break tests. Trust the comparisons between designs more
  than the absolute numbers, and keep a 2× or larger margin.

## Development

Python deps are managed with [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`); the Docker
image installs them with `uv sync --frozen`. CalculiX comes from Debian. A devcontainer is included
(with Docker-in-Docker so `fea.sh` works inside it).
See [CLAUDE.md](CLAUDE.md) for how the code is laid out.

## License

[MIT](LICENSE)
