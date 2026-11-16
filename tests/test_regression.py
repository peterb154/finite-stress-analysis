"""Real solver runs on the monitor-mount example (needs Docker). Run with: uv run pytest -m slow"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
EX = ROOT / "examples" / "monitor-mount"


def fsa_run(tmp_path, name):
    for f in (f"{name}.toml", f"{name}.step"):
        shutil.copy(EX / f, tmp_path / f)
    case = "tilt_pull_40N_top"
    subprocess.run([ROOT / "bin" / "fsa", "run", f"{name}.toml", "--coarse", "--cases", case], cwd=tmp_path, check=True)
    return json.loads((tmp_path / "runs" / name / "summary.json").read_text())["cases"][case]


@pytest.mark.slow
def test_v5_is_much_weaker_than_v8c(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    v5, v8c = fsa_run(tmp_path / "a", "v5"), fsa_run(tmp_path / "b", "v8c")
    # v5 cracked in real life; fine-mesh FEA says ~54 vs ~12 MPa.
    assert v5["vm_max"] > 3 * v8c["vm_max"]
    assert v5["vm_max"] > 30
    assert v8c["vm_max"] < 20
    assert v5["max_disp_mm"] > 3 * v8c["max_disp_mm"]


@pytest.mark.slow
def test_stl_matches_step(tmp_path):
    """v8c exported to STL should land close to the STEP result."""
    gmsh = pytest.importorskip("gmsh")
    (tmp_path / "step").mkdir()
    (tmp_path / "stl").mkdir()
    step = fsa_run(tmp_path / "step", "v8c")

    d = tmp_path / "stl"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.occ.importShapes(str(EX / "v8c.step"))
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", 2)
        gmsh.model.mesh.generate(3)  # a valid 3D mesh = a watertight skin to export
        gmsh.model.addPhysicalGroup(2, [s for _, s in gmsh.model.getEntities(2)])
        gmsh.write(str(d / "v8c.stl"))
    finally:
        gmsh.finalize()
    toml = (EX / "v8c.toml").read_text().replace('geometry = "v8c.step"', 'geometry = "v8c.stl"')
    (d / "v8c.toml").write_text(toml)
    case = "tilt_pull_40N_top"
    subprocess.run([ROOT / "bin" / "fsa", "run", "v8c.toml", "--coarse", "--cases", case], cwd=d, check=True)
    stl = json.loads((d / "runs" / "v8c" / "summary.json").read_text())["cases"][case]
    assert stl["vm_max"] == pytest.approx(step["vm_max"], rel=0.15)
    assert stl["max_disp_mm"] == pytest.approx(step["max_disp_mm"], rel=0.15)
