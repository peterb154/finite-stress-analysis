"""Load and check a part.toml. Units: mm, N, MPa. See examples/ for the format."""

import tomllib
from pathlib import Path

import numpy as np

# Rough FDM values (MPa). "inplane" = along layers, "interlayer" = pulling layers apart.
MATERIALS = {
    "PETG": dict(E=2000.0, nu=0.38, inplane=40.0, interlayer=20.0),
    "PLA": dict(E=3000.0, nu=0.36, inplane=45.0, interlayer=20.0),
    "ASA": dict(E=1900.0, nu=0.35, inplane=35.0, interlayer=17.0),
    "ABS": dict(E=1800.0, nu=0.35, inplane=33.0, interlayer=15.0),
    "PA-CF": dict(E=5000.0, nu=0.35, inplane=60.0, interlayer=25.0),
}
DEFAULT_PRINT = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}
BIG = 1e9


def load(path):
    path = Path(path)
    raw = tomllib.loads(path.read_text())
    cfg = {
        "name": raw.get("name", path.stem),
        "dir": path.parent,
        "step": path.parent / raw["step"],
        "material": material(raw.get("material", {})),
        "mesh": {"size": 5.0, "fine": 1.5, "straight_tets": True, "refine": [], **raw.get("mesh", {})},
        "cuts": raw.get("cut", []),
        "fixed": [selector(s) for s in raw.get("fixed", [])],
        "paths": {p["name"]: {**selector(p), "ref": vec(p["ref"])} for p in raw.get("load_path", [])},
        "print": {k: unit(v) for k, v in raw.get("print", DEFAULT_PRINT).items()},
        "zones": raw.get("zone", []),
    }
    if not cfg["fixed"]:
        raise ValueError(f"{path}: needs at least one [[fixed]] support")
    cfg["cases"] = {c["name"]: case_loads(c, cfg["paths"]) for c in raw.get("case", [])}
    if not cfg["cases"]:
        raise ValueError(f"{path}: needs at least one [[case]]")
    return cfg


def material(m):
    base = dict(MATERIALS[m["preset"]]) if "preset" in m else {}
    base.update({k: float(v) for k, v in m.items() if k != "preset"})
    missing = {"E", "nu", "inplane", "interlayer"} - base.keys()
    if missing:
        raise ValueError(f"material needs a preset ({', '.join(MATERIALS)}) or {sorted(missing)}")
    return base


def selector(s):
    """Surfaces picked by cylinders (hole walls, screw seats) and/or boxes."""
    cyls = []
    for c in s.get("cylinders", []):
        for p in c.get("points", [c.get("point")]):
            span = c.get("span", [-BIG, BIG])
            cyls.append(
                dict(point=vec(p), axis=unit(c["axis"]), r=float(c["r"]), span=(float(span[0]), float(span[1])))
            )
    boxes = [np.array(b, float).reshape(2, 3) for b in s.get("boxes", [])]
    if not cyls and not boxes:
        raise ValueError(f"'{s.get('name')}' selects nothing: give cylinders or boxes")
    return {"name": s.get("name", ""), "cylinders": cyls, "boxes": boxes}


def case_loads(c, paths):
    """Sum a case's loads into (force, moment about ref) per load path."""
    out = {}
    for ld in c["loads"]:
        p = paths[ld["path"]]
        f = vec(ld.get("force", [0, 0, 0]))
        at = vec(ld["at"]) if "at" in ld else p["ref"]
        m = np.cross(at - p["ref"], f) + vec(ld.get("moment", [0, 0, 0]))
        f0, m0 = out.get(ld["path"], (np.zeros(3), np.zeros(3)))
        out[ld["path"]] = (f0 + f, m0 + m)
    return out


def select(sel, nodes, xyz):
    """Return the ids in `nodes` whose points `xyz` fall in any of the selector's shapes."""
    hit = np.zeros(len(xyz), bool)
    for c in sel["cylinders"]:
        d = xyz - c["point"]
        t = d @ c["axis"]
        radial = np.linalg.norm(d - np.outer(t, c["axis"]), axis=1)
        hit |= (radial <= c["r"] + 0.05) & (t >= c["span"][0]) & (t <= c["span"][1])
    for lo, hi in sel["boxes"]:
        hit |= ((xyz >= lo) & (xyz <= hi)).all(1)
    return nodes[hit]


def vec(v):
    return np.array(v, float)


def unit(v):
    v = vec(v)
    return v / np.linalg.norm(v)
