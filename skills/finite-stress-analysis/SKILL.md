---
name: finite-stress-analysis
description: Stress-check a 3D-printed (or other) part with local FEA (gmsh + CalculiX in Docker) via the `fsa` CLI. Use when the user asks whether a part will break or bend, where it is weakest, how to make it stronger, which way to print it, or wants stress heat maps or a before/after comparison of two designs.
when_to_use: Phrases like will this break, FEA, stress analysis, finite element, is this bracket strong enough, why did my print crack, compare v1 vs v2 strength, best print orientation, stress heat map.
allowed-tools: Bash(fsa *)
---

# Finite stress analysis with `fsa`

`fsa` meshes a STEP or STL file, solves linear-static stress for each load case, and reports peak stress, deflection
and **layer tension**: stress pulling print layers apart, for each print orientation. Layer adhesion is usually
what breaks FDM parts. Everything runs in Docker with no network, on the current folder only.

`fsa` is on PATH while this plugin is enabled. If it isn't, use `${CLAUDE_PLUGIN_ROOT}/bin/fsa`.
It needs Docker running. The first run builds the image (a few minutes).

## Workflow

1. **Get the geometry** (mm). Prefer STEP: from Fusion 360 via its MCP server, or ask the user to export one.
   STL works too (downloaded models, slicer exports; see Gotchas). Put it in a project folder and run `fsa`
   from that folder (paths must be relative and inside it).
2. **Learn the geometry before writing the config.** Ask the user how the part is held and loaded:
   what bolts it down, what it carries, how heavy, and what a person might do to it (push, pull, lean).
   Get coordinates of holes and faces from the CAD (bounding box, hole centres), not by guessing.
3. **Write `part.toml`** next to the geometry file. Format: [part-toml.md](part-toml.md). Worked example:
   `${CLAUDE_PLUGIN_ROOT}/examples/monitor-mount/v8c.toml`.
4. **Coarse run first:** `fsa run part.toml --coarse` (~10-30 s). Check the printed node counts: every
   `fixed` and `load_path` must select nodes (fsa stops if one selects none). Typical: hundreds per support.
5. **Fine run:** `fsa run part.toml` (minutes). Optionally `--cases name1,name2`.
6. **Read `runs/<name>/summary.json`** and show the user the PNG heat maps it wrote
   (`<worst case>_vm.png`, `<worst case>_layer_<best orientation>.png`). Open them with the Read tool to look yourself.
7. **Iterate:** change the design, re-export, re-run, then `fsa compare runs/old runs/new` for a
   side-by-side image and a markdown table.

Other commands: `fsa render runs/<name> <case> --field vm|layer_<orientation> [--max MPa]`, `fsa --help`.

## Reading the results

- `vm_max`: peak von Mises stress (MPa), ignoring nodes within 1.5 mm of supports and load patches
  (those are artificial peaks). Compare with the material's `inplane` strength.
- `layer_tension.<orientation>.max`: compare with `interlayer` strength. `best_print_orientation` is the one
  with the lowest worst-case layer tension.
- Margin = strength / peak. Aim for **2x or more** in-plane and across layers: the material numbers are rough,
  FDM parts vary, and the model is linear and isotropic.
- `max_disp_mm`: how far it moves. Often the real complaint (a wobbly monitor) before strength is.
- Results are most trustworthy as **comparisons** between designs with the same config.
  Peaks at sharp inside corners grow as the mesh gets finer: suggest a fillet rather than trusting the number.

## Gotchas

- fsa forces CalculiX's solver single-threaded: the multithreaded solver in Debian's CalculiX gave wrong
  stresses. Don't work around it.
- Memory: about 180k nodes fits in a ~12 GB Docker VM; ~300k does not. If the run dies, raise `mesh.fine`
  or shrink the `refine` boxes.
- A rigid `load_path` makes whatever it touches infinitely stiff. Fine for a monitor or a steel bracket; for
  a soft neighbour, expect it to over-stiffen the part locally.
- Units: fsa converts STEP to mm. STL has no units and is read as mm. fsa prints the bounding box at the
  start of every run: check it against the part's real size (an inch file looks 25x too small).
- The geometry must be one solid body inside the folder you run from. Union multi-body parts in CAD first.
- STL limits: it must be watertight and not intersect itself. Downloaded models often aren't. fsa then stops
  and says to repair it (slicer repair, MeshLab, Meshmixer) or export STEP. `[[cut]]` needs STEP. Holes are
  faceted, so stresses at holes and fillets are a bit noisier than from STEP (the peak von Mises on the
  example lands within a few %). Selectors still work: they pick nodes by position, not CAD faces.
- A node can't be both fixed and in a load path (or in two load paths). fsa stops and names the pair;
  shrink a cylinder's `r`/`span` or a box.
