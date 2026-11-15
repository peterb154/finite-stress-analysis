"""Stress heat maps: two whole-part views plus two views zoomed on the peak."""

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def surface(tets):
    t = tets[:, :4]
    faces = np.concatenate([t[:, [0, 1, 2]], t[:, [0, 1, 3]], t[:, [0, 2, 3]], t[:, [1, 2, 3]]])
    _, inv, cnt = np.unique(np.sort(faces, 1), axis=0, return_inverse=True, return_counts=True)
    return faces[cnt[inv.ravel()] == 1]


def panel(ax, xyz, tris, val, vmax, elev, azim, title, box=None):
    if box is not None:
        tris = tris[((xyz[tris] >= box[0]) & (xyz[tris] <= box[1])).all(2).any(1)]
    p = xyz[tris]
    col = plt.cm.turbo(np.clip(val[tris].max(1), 0, vmax) / vmax)
    ax.add_collection3d(Poly3DCollection(p, facecolors=col, edgecolors="none"))
    lo, hi = p.reshape(-1, 3).min(0), p.reshape(-1, 3).max(0)
    ax.set_xlim(lo[0], hi[0])
    ax.set_ylim(lo[1], hi[1])
    ax.set_zlim(lo[2], hi[2])
    ax.set_box_aspect(np.maximum(hi - lo, 1e-3))
    ax.view_init(elev, azim)
    ax.set_axis_off()
    ax.set_title(title, fontsize=10)


def render(out, title, xyz, tets, val, ok, vmax):
    """`ok` masks out nodes next to supports, whose stresses are artefacts."""
    tris = surface(tets)
    val = np.maximum(val, 0)
    i = np.flatnonzero(ok)[val[ok].argmax()]
    half = max(15.0, 0.12 * np.linalg.norm(xyz.max(0) - xyz.min(0)))
    box = (xyz[i] - half, xyz[i] + half)
    fig = plt.figure(figsize=(16, 9))
    for k, (elev, azim, sub, b) in enumerate(
        [
            (25, 40, "whole part", None),
            (20, 220, "whole part, other side", None),
            (35, 35, "zoom on peak, from above", box),
            (-35, 35, "zoom on peak, from below", box),
        ]
    ):
        panel(fig.add_subplot(2, 2, k + 1, projection="3d"), xyz, tris, val, vmax, elev, azim, sub, b)
    sm = plt.cm.ScalarMappable(cmap="turbo", norm=plt.Normalize(0, vmax))
    fig.colorbar(sm, ax=fig.axes, shrink=0.6, label=f"MPa (red = at/over {vmax:g} MPa limit)")
    fig.suptitle(f"{title}  |  peak {val[i]:.1f} MPa at {xyz[i].round(1).tolist()}", fontsize=13)
    fig.savefig(out, dpi=100, bbox_inches="tight")
    plt.close(fig)


def side_by_side(out, pngs, titles):
    fig, axes = plt.subplots(1, len(pngs), figsize=(8 * len(pngs), 8))
    for ax, p, t in zip(np.atleast_1d(axes), pngs, titles):
        ax.imshow(mpimg.imread(p))
        ax.axis("off")
        ax.set_title(t, fontsize=16)
    fig.tight_layout()
    fig.savefig(out, dpi=90)
    plt.close(fig)
