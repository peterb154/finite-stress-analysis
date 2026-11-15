"""STEP -> second-order tet mesh with gmsh."""


def mesh(cfg, size, fine):
    import gmsh

    m = cfg["mesh"]
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setString("Geometry.OCCTargetUnit", "MM")
        gmsh.model.occ.importShapes(str(cfg["step"]))
        gmsh.model.occ.synchronize()
        if cfg["cuts"]:  # e.g. bore printed threads out to heat-set insert holes
            tools = [(3, gmsh.model.occ.addCylinder(*c["start"], *c["vector"], c["r"])) for c in cfg["cuts"]]
            gmsh.model.occ.cut(gmsh.model.getEntities(3), tools)
            gmsh.model.occ.synchronize()

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
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        # Straight-sided tet10s can't invert; curved ones did on some parts.
        gmsh.option.setNumber("Mesh.SecondOrderLinear", int(bool(m["straight_tets"])))
        gmsh.model.mesh.generate(3)

        tags, xyz, _ = gmsh.model.mesh.getNodes()
        _, _, enodes = gmsh.model.mesh.getElements(3)
        tets = enodes[0].reshape(-1, 10)[:, [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]]  # gmsh -> CalculiX tet10 order
        _, _, fnodes = gmsh.model.mesh.getElements(2)
        tris = fnodes[0].reshape(-1, 6)[:, :3]
    finally:
        gmsh.finalize()
    return tags.astype(int), xyz.reshape(-1, 3), tets.astype(int), tris.astype(int)
