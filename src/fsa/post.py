"""Stress measures, peak reporting and .vtu I/O."""

import re

import numpy as np
from scipy.spatial import cKDTree

from .config import UserError

BC_EXCLUDE_MM = 1.5  # supports/rigid patches cause artificial peaks: ignore nodes this close


def von_mises(s):
    sxx, syy, szz, sxy, syz, szx = s.T
    return np.sqrt(0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2) + 3 * (sxy**2 + syz**2 + szx**2))


def normal_stress(s, n):
    """Normal stress along unit vector n: layer tension when n is the build direction."""
    sxx, syy, szz, sxy, syz, szx = s.T
    T = np.stack([np.stack([sxx, sxy, szx], -1), np.stack([sxy, syy, syz], -1), np.stack([szx, syz, szz], -1)], -2)
    return np.einsum("i,nij,j->n", n, T, n)


def near_bc(xyz, bc_points):
    """Nodes within BC_EXCLUDE_MM of any support/load-patch node (exact, no sampling)."""
    hits = cKDTree(bc_points).query_ball_point(xyz, BC_EXCLUDE_MM, return_length=True)
    return hits > 0


def peak(val, xyz, ok):
    if not ok.any():
        raise UserError(
            f"every node is within {BC_EXCLUDE_MM} mm of a support or load patch: the selectors cover too much"
        )
    i = np.flatnonzero(ok)[val[ok].argmax()]
    return float(val[i]), xyz[i].round(1).tolist()


def write_vtu(path, xyz, tets, fields):
    """`tets` are 0-based indices into xyz."""
    with open(path, "w") as fp:
        fp.write('<VTKFile type="UnstructuredGrid" version="0.1">\n<UnstructuredGrid>\n')
        fp.write(f'<Piece NumberOfPoints="{len(xyz)}" NumberOfCells="{len(tets)}">\n<Points>\n')
        fp.write('<DataArray type="Float32" NumberOfComponents="3" format="ascii">\n')
        np.savetxt(fp, xyz, fmt="%.4f")
        fp.write("</DataArray>\n</Points>\n<Cells>\n")
        fp.write('<DataArray type="Int32" Name="connectivity" format="ascii">\n')
        np.savetxt(fp, tets, fmt="%d")
        fp.write('</DataArray>\n<DataArray type="Int32" Name="offsets" format="ascii">\n')
        np.savetxt(fp, np.arange(1, len(tets) + 1) * 10, fmt="%d")
        fp.write('</DataArray>\n<DataArray type="UInt8" Name="types" format="ascii">\n')
        np.savetxt(fp, np.full(len(tets), 24), fmt="%d")
        fp.write("</DataArray>\n</Cells>\n<PointData>\n")
        for name, arr in fields.items():
            nc = 1 if arr.ndim == 1 else arr.shape[1]
            fp.write(f'<DataArray type="Float32" Name="{name}" NumberOfComponents="{nc}" format="ascii">\n')
            np.savetxt(fp, arr.reshape(len(xyz), -1), fmt="%.4g")
            fp.write("</DataArray>\n")
        fp.write("</PointData>\n</Piece>\n</UnstructuredGrid>\n</VTKFile>\n")


def read_vtu(path):
    with open(path) as fp:
        txt = fp.read()
    arrays = {}
    for m in re.finditer(r"<DataArray([^>]*)>\n(.*?)</DataArray>", txt, re.DOTALL):
        nm = re.search(r'Name="([^"]+)"', m.group(1))
        arrays[nm.group(1) if nm else "points"] = m.group(2)
    xyz = np.array(arrays.pop("points").split(), float).reshape(-1, 3)
    tets = np.array(arrays.pop("connectivity").split(), int).reshape(-1, 10)
    arrays.pop("offsets"), arrays.pop("types")
    return xyz, tets, {k: np.array(v.split(), float) for k, v in arrays.items()}
