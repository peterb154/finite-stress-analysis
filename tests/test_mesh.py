"""STL input, meshed with the host's gmsh (no Docker)."""

import numpy as np
import pytest

from fsa import cli, config
from fsa.mesh import mesh

gmsh = pytest.importorskip("gmsh")

MESH = {"size": 4.0, "fine": 4.0, "straight_tets": True, "refine": []}


def write_stl(path, build):
    """Build an OCC solid, 3D-mesh it, and save its boundary as STL (a valid 3D mesh = a watertight skin)."""
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        build(gmsh.model.occ)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", 2)
        gmsh.model.mesh.generate(3)
        gmsh.model.addPhysicalGroup(2, [s for _, s in gmsh.model.getEntities(2)])
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def cube_with_hole(occ):
    occ.cut([(3, occ.addBox(0, 0, 0, 20, 20, 20))], [(3, occ.addCylinder(10, 10, -1, 0, 0, 22, 4))])


def test_stl_meshes_and_selectors_pick_nodes(tmp_path):
    stl = tmp_path / "cube.stl"
    write_stl(stl, cube_with_hole)
    ids, xyz, tets, tris = mesh({"geometry": stl, "mesh": MESH, "cuts": []}, 4.0, 4.0)
    assert tets.shape[1] == 10 and len(tets) > 100
    assert np.allclose(xyz.min(0), 0, atol=0.01) and np.allclose(xyz.max(0), 20, atol=0.01)

    idx = np.zeros(ids.max() + 1, int)
    idx[ids] = np.arange(len(ids))
    surf = np.unique(tris)
    hole = config.selector({"cylinders": [{"point": [10, 10, 0], "axis": [0, 0, 1], "r": 4, "span": [1, 19]}]})
    base = config.selector({"boxes": [[-1, -1, -1, 21, 21, 0.01]]})
    cfg = {"fixed": [base], "paths": {"pin": {**hole, "ref": np.array([10.0, 10, 10])}}}
    fixed, paths = cli.select_bcs(cfg, surf, xyz[idx[surf]])
    assert len(fixed) > 20 and len(paths["pin"][0]) > 20


def test_open_stl_says_how_to_fix_it(tmp_path):
    # A cube with its top face missing: not watertight.
    v = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]) * 20.0
    faces = [(0, 2, 1), (0, 3, 2), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4)]
    lines = ["solid open"]
    for f in faces:
        lines += ["facet normal 0 0 0", "outer loop", *(f"vertex {x} {y} {z}" for x, y, z in v[list(f)])]
        lines += ["endloop", "endfacet"]
    stl = tmp_path / "open.stl"
    stl.write_text("\n".join([*lines, "endsolid open"]) + "\n")
    with pytest.raises(ValueError, match="watertight"):
        mesh({"geometry": stl, "mesh": MESH, "cuts": []}, 4.0, 4.0)
