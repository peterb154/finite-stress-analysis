"""Render stress maps from a run's results.vtu.

Usage: python3 render.py <name> <field> <limit_MPa> [<field> <limit> ...]
Field names are the PointData names in results.vtu, e.g. 5_tilt_pull_40N_top_vm.
"""
import re
import sys

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402


def read_vtu(path):
    txt = open(path).read()
    arrays = {}
    for m in re.finditer(r'<DataArray([^>]*)>\n(.*?)</DataArray>', txt, re.S):
        nm = re.search(r'Name="([^"]+)"', m.group(1))
        arrays[nm.group(1) if nm else "points"] = m.group(2)
    xyz = np.array(arrays.pop("points").split(), float).reshape(-1, 3)
    tets = np.array(arrays.pop("connectivity").split(), int).reshape(-1, 10)
    arrays.pop("offsets"), arrays.pop("types")
    fields = {k: np.array(v.split(), float) for k, v in arrays.items()}
    return xyz, tets, fields


def surface(tets):
    t = tets[:, :4]
    faces = np.concatenate([t[:, [0, 1, 2]], t[:, [0, 1, 3]], t[:, [0, 2, 3]], t[:, [1, 2, 3]]])
    key = np.sort(faces, 1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    return faces[cnt[inv.ravel()] == 1]


def panel(ax, xyz, tris, val, vmax, elev, azim, title, xmax=None):
    if xmax is not None:
        tris = tris[(xyz[tris][:, :, 0] < xmax).all(1)]
    p = xyz[tris]
    col = plt.cm.turbo(np.clip(val[tris].max(1), 0, vmax) / vmax)
    ax.add_collection3d(Poly3DCollection(p, facecolors=col, edgecolors="none"))
    lo, hi = p.reshape(-1, 3).min(0), p.reshape(-1, 3).max(0)
    ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(lo[2], hi[2])
    ax.set_box_aspect(hi - lo)
    ax.view_init(elev, azim)
    ax.set_axis_off()
    ax.set_title(title, fontsize=10)


def render(name, field, vmax, xyz, tris, fields, out):
    val = np.maximum(fields[field], 0)
    fig = plt.figure(figsize=(16, 9))
    panel(fig.add_subplot(2, 2, 1, projection="3d"), xyz, tris, val, vmax, 25, 40, "whole part, arm side")
    panel(fig.add_subplot(2, 2, 2, projection="3d"), xyz, tris, val, vmax, 20, 220, "whole part, monitor side")
    panel(fig.add_subplot(2, 2, 3, projection="3d"), xyz, tris, val, vmax, 35, 35,
          "ZOOM plate + block (x<16), from above", xmax=16)
    panel(fig.add_subplot(2, 2, 4, projection="3d"), xyz, tris, val, vmax, -35, 35,
          "ZOOM plate + block (x<16), from below", xmax=16)
    sm = plt.cm.ScalarMappable(cmap="turbo", norm=plt.Normalize(0, vmax))
    fig.colorbar(sm, ax=fig.axes, shrink=0.6, label=f"MPa (red = at/over {vmax} MPa limit)")
    fig.suptitle(f"{name}  |  {field}  |  raw max {fields[field].max():.1f} MPa (incl. bolt/fixed spots; see summary.json for the real peak)", fontsize=13)
    fig.savefig(out, dpi=100, bbox_inches="tight")
    plt.close(fig)


def main():
    name = sys.argv[1]
    xyz, tets, fields = read_vtu(f"runs/{name}/results.vtu")
    tris = surface(tets)
    args = sys.argv[2:]
    for field, lim in zip(args[::2], args[1::2]):
        out = f"runs/{name}/{field}.png"
        render(name, field, float(lim), xyz, tris, fields, out)
        print("wrote", out)


if __name__ == "__main__":
    main()
