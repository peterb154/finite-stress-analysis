"""STEP or STL -> second-order tet mesh with gmsh."""

import math

import numpy as np

# Rebuilding surfaces from STL triangles fails at some feature angles and works at others,
# depending on the part (v8c: 40 and 60 deg fail, 20 and 89 work). Try these in turn.
STL_ANGLES = (40, 20, 89)
STL_HELP = (
    "could not build a solid from this STL. It is probably not watertight or it intersects itself. "
    "Repair it (slicer repair, MeshLab, Meshmixer) or export STEP from CAD"
)


class BadMesh(Exception):
    """gmsh finished without error but the tets are wrong: none at all (open STL) or the wrong volume."""


def mesh(cfg, size, fine):
    import gmsh

    geo = cfg["geometry"]
    if not geo.is_file():
        raise FileNotFoundError(
            f"{geo} not found. It must be inside the folder fsa runs from (the container sees nothing else)."
        )
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        if geo.suffix.lower() == ".stl":
            mesh_stl(gmsh, geo, cfg["mesh"], size, fine)
        else:
            load_step(gmsh, geo, cfg["cuts"])
            print_bounding_box(gmsh, geo)
            generate(gmsh, cfg["mesh"], size, fine)

        tags, xyz, _ = gmsh.model.mesh.getNodes()
        _, _, enodes = gmsh.model.mesh.getElements(3)
        tets = enodes[0].reshape(-1, 10)[:, [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]]  # gmsh -> CalculiX tet10 order
        _, _, fnodes = gmsh.model.mesh.getElements(2)
        tris = fnodes[0].reshape(-1, 6)[:, :3]
    finally:
        gmsh.finalize()
    return tags.astype(int), xyz.reshape(-1, 3), tets.astype(int), tris.astype(int)


def load_step(gmsh, path, cuts):
    gmsh.option.setString("Geometry.OCCTargetUnit", "MM")
    gmsh.model.occ.importShapes(str(path))
    gmsh.model.occ.synchronize()
    vols = gmsh.model.getEntities(3)
    if len(vols) != 1:
        raise ValueError(
            f"{path.name} has {len(vols)} solid bodies; fsa needs exactly one. "
            "Combine (boolean union) the bodies in CAD and re-export."
        )
    if cuts:  # e.g. bore printed threads out to heat-set insert holes
        tools = [(3, gmsh.model.occ.addCylinder(*c["start"], *c["vector"], c["r"])) for c in cuts]
        gmsh.model.occ.cut(gmsh.model.getEntities(3), tools)
        gmsh.model.occ.synchronize()


def mesh_stl(gmsh, path, m, size, fine):
    """STL has no units (assumed mm) and no CAD faces: rebuild surfaces from the triangles, remesh at
    the requested size, and close them into one volume. Last resort: keep the STL's own triangles."""
    gmsh.merge(str(path))
    print_bounding_box(gmsh, path)
    _, corners, tri = stl_triangles(gmsh)
    stl_vol = solid_volume(path, corners, connected_triangles(tri))
    longest = np.linalg.norm(corners - np.roll(corners, 1, axis=1), axis=2).max()
    errors = []
    for angle in [*STL_ANGLES, None]:
        gmsh.finalize()  # a failed attempt leaves state behind that gmsh.clear() doesn't reset
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.merge(str(path))
        try:
            if angle is None:
                loops = [gmsh.model.geo.addSurfaceLoop([s]) for s in split_shells(gmsh)]
            else:
                gmsh.model.mesh.classifySurfaces(angle * math.pi / 180, True, True, math.pi)
                gmsh.model.mesh.createGeometry()
                loops = [gmsh.model.geo.addSurfaceLoop([s for _, s in gmsh.model.getEntities(2)])]
            gmsh.model.geo.addVolume(loops)  # first loop is the outside, the rest are holes
            gmsh.model.geo.synchronize()
            generate(gmsh, m, size, fine, from_curvature=0)  # facets look curved everywhere
            check_volume(gmsh, stl_vol)
            if angle is None:  # last, so an open or broken STL gets the "repair it" message instead
                check_facet_size(path, longest, size)
        except Exception as e:
            if type(e) not in (Exception, BadMesh):  # gmsh raises plain Exception; anything else is a bug
                raise
            errors.append(f"{angle or 'raw'}: {e}")
            continue
        if angle is None:
            print(
                f"{path.name}: couldn't remesh the surface, so the mesh follows the STL's own triangles "
                "(mesh.size/fine only apply inside)."
            )
        return
    raise ValueError(f"{path.name}: {STL_HELP}. gmsh said: {'; '.join(errors)}")


def stl_triangles(gmsh):
    """The merged STL's surfaces (one per `solid` block), triangle corners (n, 3, 3) and node tags (n, 3)."""
    surfs = gmsh.model.getEntities(2)
    tags, xyz, _ = gmsh.model.mesh.getNodes(-1, -1, True)
    tags = tags.astype(int)
    idx = np.zeros(tags.max() + 1, int)
    idx[tags] = np.arange(len(tags))
    tri = np.concatenate([gmsh.model.mesh.getElements(2, s)[2][0] for _, s in surfs]).reshape(-1, 3).astype(int)
    return surfs, xyz.reshape(-1, 3)[idx[tri]], tri


def check_facet_size(path, longest, size):
    """The raw fallback keeps the STL's triangles. CAD exports have long thin facets (Fusion's v8c: up to
    118 mm), which make bad tets and starve the support/load patches of nodes: 215 MPa where STEP says 12.
    With facets no longer than the mesh size, raw matched STEP (12.1 vs 11.7 MPa)."""
    if longest > 2 * size:
        raise ValueError(
            f"{path.name}: gmsh couldn't remesh this STL, and its own triangles are too coarse to use "
            f"(up to {longest:.0f} mm long, mesh size {size:g} mm): the results would be wrong. Use STEP, or "
            f"re-export the STL with a maximum edge length of about {size:g} mm "
            "(Fusion: Refinement > Custom > Maximum Edge Length)."
        )


def solid_volume(path, corners, shell):
    """Volume of the solid the STL describes: the outer shell minus the others (internal voids).
    Per-shell abs() so it doesn't depend on which way the STL's triangles are wound."""
    shells = []
    for k in np.unique(shell):
        c = corners[shell == k]
        vol = abs(np.einsum("ij,ij->i", c[:, 0], np.cross(c[:, 1], c[:, 2])).sum()) / 6
        shells.append((vol, c.reshape(-1, 3).min(0), c.reshape(-1, 3).max(0)))
    shells.sort(key=lambda s: s[0], reverse=True)
    (outer, lo, hi), voids = shells[0], shells[1:]
    apart = sum(not ((v_lo >= lo).all() and (v_hi <= hi).all()) for _, v_lo, v_hi in voids)
    if apart:
        raise ValueError(
            f"{path.name} has {apart + 1} separate bodies; fsa needs exactly one. "
            "Combine (boolean union) the bodies in CAD and re-export."
        )
    return outer - sum(v for v, _, _ in voids)


def split_shells(gmsh):
    """Put each closed shell of the STL (outer skin, internal voids) on its own surface, keeping the
    triangles. One surface loop for all of them fills the voids and orphans their nodes. Outer shell first."""
    stl_surfs, corners, tri = stl_triangles(gmsh)
    tags, xyz, _ = gmsh.model.mesh.getNodes(-1, -1, True)
    xyz = dict(zip(tags.astype(int), xyz.reshape(-1, 3)))
    shell = connected_triangles(tri)
    gmsh.model.removeEntities(stl_surfs, recursive=True)  # also drops their nodes: add them back per shell
    surfs = []
    for k in np.unique(shell):
        t = tri[shell == k]
        nodes = np.unique(t)
        s = gmsh.model.addDiscreteEntity(2)
        gmsh.model.mesh.addNodes(2, s, nodes, np.array([xyz[n] for n in nodes]).ravel())
        gmsh.model.mesh.addElementsByType(s, 2, [], t.ravel())
        lo, hi = corners[shell == k].reshape(-1, 3).min(0), corners[shell == k].reshape(-1, 3).max(0)
        surfs.append((np.prod(hi - lo), s))
    return [s for _, s in sorted(surfs, reverse=True)]


def connected_triangles(tri):
    """Label each triangle with its connected piece (triangles sharing a node are connected)."""
    parent = {}

    def root(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b, c in tri:
        rc = root(c)
        parent[root(a)] = rc
        parent[root(b)] = rc
    return np.array([root(a) for a in tri[:, 0]])


def check_volume(gmsh, expected, rel=0.02):
    tags, xyz, _ = gmsh.model.mesh.getNodes()
    tags = tags.astype(int)
    idx = np.zeros(tags.max() + 1, int)
    idx[tags] = np.arange(len(tags))
    _, _, e = gmsh.model.mesh.getElements(3)
    p = xyz.reshape(-1, 3)[idx[e[0].reshape(-1, 10)[:, :4].astype(int)]]
    vol = abs(np.einsum("ij,ij->i", p[:, 1] - p[:, 0], np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 0]))).sum() / 6
    if abs(vol - expected) > rel * expected:
        raise BadMesh(f"meshed volume {vol:.0f} mm3, but the STL encloses {expected:.0f} (a void filled or lost)")


def generate(gmsh, m, size, fine, from_curvature=12):
    f = gmsh.model.mesh.field
    boxes = []
    for lo_hi in m["refine"]:
        b = f.add("Box")
        x0, y0, z0, x1, y1, z1 = lo_hi
        for k, v in dict(
            VIn=fine, VOut=size, XMin=x0, XMax=x1, YMin=y0, YMax=y1, ZMin=z0, ZMax=z1, Thickness=4
        ).items():
            f.setNumber(b, k, v)
        boxes.append(b)
    if boxes:
        mn = f.add("Min")
        f.setNumbers(mn, "FieldsList", boxes)
        f.setAsBackgroundMesh(mn)
    gmsh.option.setNumber("Mesh.MeshSizeMax", size)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", from_curvature)
    gmsh.option.setNumber("Mesh.ElementOrder", 2)
    # Straight-sided tet10s can't invert; curved ones did on some parts.
    gmsh.option.setNumber("Mesh.SecondOrderLinear", int(bool(m["straight_tets"])))
    gmsh.model.mesh.generate(3)
    if len(gmsh.model.mesh.getElements(3)[0]) == 0:  # an open STL "meshes" fine, with no volume elements
        raise BadMesh("no volume elements: the surface is not closed")


def print_bounding_box(gmsh, path):
    b = gmsh.model.getBoundingBox(-1, -1)
    lo, hi = (", ".join(f"{x:.1f}" for x in v) for v in (b[:3], b[3:]))
    print(f"{path.name}: bounding box [{lo}] to [{hi}] mm (an inch file looks 25x too small)")
