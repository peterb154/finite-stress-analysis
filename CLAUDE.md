# CLAUDE.md

## Layout

- `src/fsa/`: the package. `config.py` (part.toml → dict, material presets, surface selectors),
  `mesh.py` (gmsh: STEP via OpenCASCADE, STL rebuilt from its triangles), `solve.py` (CalculiX deck, run,
  read .frd), `post.py` (stress measures, .vtu I/O), `render.py` (heat maps), `cli.py` (`fsa run|render|compare`).
- `bin/fsa`: host wrapper. Builds the Docker image from this repo and runs `fsa` in it on `$PWD`
  (`--network none`). The plugin puts `bin/` on Claude's PATH.
- `skills/finite-stress-analysis/`: the Claude Code skill (`SKILL.md`) + config reference (`part-toml.md`).
- `.claude-plugin/`: plugin + marketplace manifests (the repo is its own marketplace).
- `examples/monitor-mount/`: v5 (failed design) and v8c (fixed design). The regression check.

## Units and frame

mm, N, MPa, in the geometry file's own frame. STL has no units and is read as mm.

## Rules

- Python deps: uv only. Edit `pyproject.toml`, bump `[tool.uv] exclude-newer` (2 days back), `uv lock`.
  gmsh's Python module comes from apt inside Docker (no linux-aarch64 wheel on PyPI).
- CalculiX must stay single-threaded (`solve.run_ccx` forces it). Multithreaded spooles gave wrong answers.
- After changing solver code: `uv run pytest -m slow`, and a fine run of both examples should stay close to
  examples/monitor-mount/README.md (v5 tilt-pull ~54 MPa, v8c push-down ~12.5 MPa).
- Peak stresses next to supports, load patches and sharp corners are partly artefacts. fsa excludes nodes
  within 1.5 mm of supports and load patches. Look at the heat map, not just the number.
- STL meshing (`mesh.mesh_stl`) tries several `classifySurfaces` angles, then the raw triangles. Which
  angle works depends on the part. Restart gmsh between attempts: `gmsh.clear()` leaves state behind and
  later attempts mesh to nothing. An open STL "meshes" without error but gives no tets, so check for that.
  Remeshing is flaky ("overlapping facets"), and which angles work changes with the gmsh build (Docker has
  Debian's 4.8, the host wheel is 4.15) and the STL. Fusion's v8c STL never remeshes in Docker, so it uses raw.
  Raw splits the STL into shells (outer skin + internal voids): one surface loop for all of them fills the
  voids and leaves their nodes out of every tet. Every attempt checks the tet volume against the STL's.
  Raw is only as good as the STL's triangles: a 2 mm STL matched STEP, Fusion's (facets up to 118 mm) gave
  215 vs 12 MPa. So raw refuses facets longer than 2x mesh size and asks for a finer export or STEP.
- Memory (CalculiX peak, fine v8c in Docker): 168k nodes 4.5 GB, 327k nodes 11.4 GB (12 min). It grows
  faster than the node count; a 12.5 GB Docker VM tops out around 330k.
- Bad input (part.toml, geometry) raises `config.UserError`: `fsa` prints just the message. Anything else
  keeps its traceback, so bugs stay loud. Don't catch plain `ValueError`.
- Tests: `tests/test_mesh.py` uses the host's gmsh wheel (no Docker); `-m slow` uses Docker via `bin/fsa`.
- Bump `version` in `.claude-plugin/plugin.json` when the plugin changes, or installed users won't get updates.
- `runs/` is gitignored. Copy any image worth keeping into `docs/`.
