import pytest


@pytest.fixture
def write_stl():
    """write_stl(path, build): build an OCC solid with build(gmsh.model.occ), or import a STEP if build is a
    path, 3D-mesh it and save the boundary as STL. A valid 3D mesh means a watertight skin."""
    gmsh = pytest.importorskip("gmsh")

    def write(path, build):
        gmsh.initialize()
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            if callable(build):
                build(gmsh.model.occ)
            else:
                gmsh.model.occ.importShapes(str(build))
            gmsh.model.occ.synchronize()
            gmsh.option.setNumber("Mesh.MeshSizeMax", 2)
            gmsh.model.mesh.generate(3)
            gmsh.model.addPhysicalGroup(2, [s for _, s in gmsh.model.getEntities(2)])
            gmsh.write(str(path))
        finally:
            gmsh.finalize()

    return write
