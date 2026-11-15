# part.toml reference

Units: mm, N, MPa. Coordinates are the STEP file's own frame. Paths are relative to the toml file.

```toml
name = "bracket_v2"       # optional; default = file name. Output goes to runs/<name>/
step = "bracket_v2.step"

[material]
preset = "PETG"           # PETG | PLA | ASA | ABS | PA-CF
# Override or replace the preset (MPa): E, nu, inplane (along layers), interlayer (across layers)
# interlayer = 15

[mesh]
size = 5.0                # element size away from refine boxes
fine = 1.5                # element size inside refine boxes
straight_tets = true      # avoids inverted elements; leave on
refine = [[xmin, ymin, zmin, xmax, ymax, zmax]]   # optional: where you expect trouble

# Supports: surfaces held completely still (bolted to something rigid). At least one.
[[fixed]]
name = "wall_bolts"
boxes = [[x0, y0, z0, x1, y1, z1]]      # surface nodes inside any box
[[fixed.cylinders]]                     # surface nodes on a cylinder wall, e.g. bolt holes
points = [[x, y, z], [x, y, z]]         # one point on each hole's axis (or `point = [...]` for one)
axis = [1, 0, 0]                        # hole direction
r = 2.8                                 # hole radius (nodes within r + 0.05 of the axis)
span = [36.5, 1e9]                      # optional: only along-axis distances from `point` in this range

# Load paths: where the load comes in. Each is a rigid body on the selected surfaces,
# driven at `ref` (a point inside whatever pushes on the part). Same selectors as [[fixed]].
[[load_path]]
name = "shelf"
ref = [0, 50, 100]
[[load_path.cylinders]]
point = [0, 20, 30]
axis = [0, 0, 1]
r = 3.5

# Load cases: each is solved separately. Loads in one case add up.
# force in N; `at` = where the force acts (default: ref) -> moment about ref is computed for you.
# Optional `moment` in N*mm.
[[case]]
name = "shelf_full"
loads = [{ path = "shelf", force = [0, 0, -100] },
         { path = "shelf", force = [-20, 0, 0], at = [0, 50, 200] }]

# Layer-stacking direction for each print orientation to check (default: x, y, z).
[print]
flat = [0, 0, 1]
on_side = [1, 0, 0]

# Optional: extra peak stress reported for a region.
[[zone]]
name = "neck"
box = [x0, y0, z0, x1, y1, z1]

# Optional: cylinders cut out of the CAD before meshing (e.g. printed threads -> insert holes).
[[cut]]
start = [40, 11.85, -26.15]
vector = [25, 0, 0]
r = 2.8
```

Inline tables `{ ... }` must stay on one line (TOML 1.0). Use `[[fixed.cylinders]]` sub-tables for long ones.

## Choosing loads

- Weight: mass × 9.81 N, downward, at the centre of mass.
- People: 100 N pushing down on an edge, 40 N pushing or pulling sideways at the far edge. These are
  the bumps and leans that actually break mounts.
- Put the force where it really acts (`at`). A lever arm multiplies the moment, and the moment is usually what breaks things.
