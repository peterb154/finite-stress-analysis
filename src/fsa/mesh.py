"""STEP or STL -> second-order tet mesh with gmsh."""

import math

# Rebuilding surfaces from STL triangles fails at some feature angles and works at others,
# depending on the part (v8c: 40 and 60 deg fail, 20 and 89 work). Try these in turn.
STL_ANGLES = (40, 20, 89)
STL_HELP = (
    "could not build a solid from this STL. It is probably not watertight or it intersects itself. "
    "Repair it (slicer repair, MeshLab, Meshmixer) or export STEP from CAD"
)


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
    errors = []
    for angle in [*STL_ANGLES, None]:
        gmsh.finalize()  # a failed attempt leaves state behind that gmsh.clear() doesn't reset
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.merge(str(path))
        if angle is None:
            print(f"{path.name}: remeshing the surface failed; meshing on the STL's own triangles")
        try:
            if angle is not None:
                gmsh.model.mesh.classifySurfaces(angle * math.pi / 180, True, True, math.pi)
                gmsh.model.mesh.createGeometry()
            surfs = [s for _, s in gmsh.model.getEntities(2)]
            gmsh.model.geo.addVolume([gmsh.model.geo.addSurfaceLoop(surfs)])
            gmsh.model.geo.synchronize()
            if not errors:
                print_bounding_box(gmsh, path)
            generate(gmsh, m, size, fine, from_curvature=0)  # facets look curved everywhere
            return
        except Exception as e:  # noqa: BLE001 - gmsh raises plain Exception
            errors.append(f"{angle or 'raw'}: {e}")
    raise ValueError(f"{path.name}: {STL_HELP}. gmsh said: {'; '.join(errors)}")


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
        raise ValueError("no volume elements: the surface is not closed")


def print_bounding_box(gmsh, path):
    b = gmsh.model.getBoundingBox(-1, -1)
    lo, hi = (", ".join(f"{x:.1f}" for x in v) for v in (b[:3], b[3:]))
    print(f"{path.name}: bounding box [{lo}] to [{hi}] mm (an inch file looks 25x too small)")
