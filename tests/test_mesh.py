"""STL input, meshed with the host's gmsh (no Docker)."""

import numpy as np
import pytest

from fsa import cli, config
from fsa import mesh as fsa_mesh
from fsa.mesh import mesh

pytest.importorskip("gmsh")

MESH = {"size": 4.0, "fine": 4.0, "straight_tets": True, "refine": []}


def cube_with_hole(occ):
    occ.cut([(3, occ.addBox(0, 0, 0, 20, 20, 20))], [(3, occ.addCylinder(10, 10, -1, 0, 0, 22, 4))])


def test_stl_meshes_and_selectors_pick_nodes(tmp_path, write_stl):
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


def box_with_void(occ):
    # A closed 8 mm cavity inside a 20 mm cube: the STL has two shells (outer skin + void).
    occ.cut([(3, occ.addBox(0, 0, 0, 20, 20, 20))], [(3, occ.addBox(6, 6, 6, 8, 8, 8))])


@pytest.mark.parametrize("angles", [fsa_mesh.STL_ANGLES, ()], ids=["remesh", "raw"])
def test_stl_with_internal_void(tmp_path, write_stl, monkeypatch, angles):
    monkeypatch.setattr(fsa_mesh, "STL_ANGLES", angles)  # () forces the raw-triangle fallback
    stl = tmp_path / "void.stl"
    write_stl(stl, box_with_void)
    ids, xyz, tets, _ = mesh({"geometry": stl, "mesh": MESH, "cuts": []}, 4.0, 4.0)

    idx = np.zeros(ids.max() + 1, int)
    idx[ids] = np.arange(len(ids))
    p = xyz[idx[tets[:, :4]]]
    vol = abs(np.einsum("ij,ij->i", p[:, 1] - p[:, 0], np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 0]))).sum() / 6
    assert vol == pytest.approx(20**3 - 8**3, rel=0.01)  # the void stays empty
    assert set(ids) == set(np.unique(tets))  # every node is in a tet, or CalculiX drops it from the results


def test_raw_fallback_refuses_coarse_facets(tmp_path, monkeypatch):
    # 12 big triangles, like a CAD export of a box: kept as-is they'd give bad tets and wrong stresses.
    monkeypatch.setattr(fsa_mesh, "STL_ANGLES", ())
    gmsh = pytest.importorskip("gmsh")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.occ.addBox(0, 0, 0, 40, 40, 40)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMin", 100)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 100)
        gmsh.model.mesh.generate(2)
        stl = tmp_path / "box.stl"
        gmsh.write(str(stl))
    finally:
        gmsh.finalize()
    with pytest.raises(ValueError, match="too coarse"):
        mesh({"geometry": stl, "mesh": MESH, "cuts": []}, 4.0, 4.0)


def ascii_stl(path, blocks):
    """blocks: one list of (3, 3) triangles per `solid ... endsolid` block."""
    lines = []
    for k, tris in enumerate(blocks):
        lines.append(f"solid b{k}")
        for t in tris:
            lines += ["facet normal 0 0 0", "outer loop", *(f"vertex {x} {y} {z}" for x, y, z in t)]
            lines += ["endloop", "endfacet"]
        lines.append(f"endsolid b{k}")
    path.write_text("\n".join(lines) + "\n")


def cube(origin, side):
    v = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]])
    v = np.asarray(origin, float) + v * side
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4)]
    faces += [(1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return [v[list(f)] for f in faces]


def test_stl_with_several_solid_blocks(tmp_path):
    # Some exporters write one `solid` block per body or colour: here one cube split over two blocks.
    c = cube([0, 0, 0], 8.0)
    stl = tmp_path / "blocks.stl"
    ascii_stl(stl, [c[:6], c[6:]])
    _, _, tets, _ = mesh({"geometry": stl, "mesh": MESH, "cuts": []}, 4.0, 4.0)
    assert len(tets) > 10


def test_stl_with_two_bodies_says_union_them(tmp_path):
    stl = tmp_path / "two.stl"
    ascii_stl(stl, [cube([0, 0, 0], 8.0) + cube([20, 0, 0], 8.0)])
    with pytest.raises(ValueError, match="2 separate bodies"):
        mesh({"geometry": stl, "mesh": MESH, "cuts": []}, 4.0, 4.0)
