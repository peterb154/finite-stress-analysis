# Example: HP 32s monitor → VESA 100 adapter

A 3D-printed PETG adapter between an HP 32s monitor (no VESA holes, HP quick-release pocket) and a
VESA 100 wall arm.

- **v5** (`v5.step`, `v5.toml`): the original. Its four load screws sat on a 3 mm plate cantilevered off
  a central block. It cracked twice along the plate/block junction, following a layer line.
- **v8c** (`v8c.step`, `v8c.toml`): the redesign. It has a 9 mm backing plate with counterbored screws,
  a spider dropped to sit level with the tabs, heat-set inserts, and a sloped top so it still rocks into
  the monitor's pocket. `build_v8c.py` is the Fusion 360 script that builds it.

```sh
cd examples/monitor-mount
fsa run v5.toml && fsa run v8c.toml
fsa compare runs/v5 runs/v8c --case tilt_pull_40N_top
```

Fine-mesh results (MPa, ignoring the bolt/seat patches):

| case | v5 | v8c |
|---|---|---|
| weight (49 N) | 8.6 | 3.5 |
| push down 100 N | 34.6 | 12.5 |
| pull top edge 40 N | **53.7** | 11.7 |
| twist 40 N | 29.5 | 6.8 |

The FEA puts v5's peak where it actually broke. v8c was printed on 2026-11-15; its fit test is still pending.
