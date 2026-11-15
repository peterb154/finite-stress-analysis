from pathlib import Path

import numpy as np

from fsa import solve

DATA = Path(__file__).parent / "data"


def test_read_frd_two_steps():
    # Trimmed from a real CalculiX 2.20 run. Note values that run together: "1-2.56493E-03-3.77957E-03".
    steps = solve.read_frd(DATA / "two_steps.frd")
    assert len(steps) == 2
    assert steps[0]["DISP"][1] == [-2.56493e-03, -3.77957e-03, -1.27650e-03]
    assert steps[1]["STRESS"][3][:6] == [-7.99879e-02, 3.39490e-01, 1.13065, -1.60479e-02, 7.26260e-01, 1.10868e-01]


def test_write_inp_rigid_load_path_and_moment(tmp_path):
    ids = np.arange(1, 11)
    xyz = np.random.default_rng(0).random((10, 3))
    tets = ids.reshape(1, 10)
    fixed = np.array([1, 2, 3])
    paths = {"hook": (np.array([7, 8, 9]), np.array([0.0, 0.0, 50.0]))}
    cases = {
        "a": {"hook": (np.array([0, 0, -10.0]), np.array([0, 100.0, 0]))},
        "b": {"hook": (np.array([5.0, 0, 0]), np.zeros(3))},
    }
    solve.write_inp(tmp_path / "m.inp", ids, xyz, tets, fixed, paths, cases, {"E": 2000.0, "nu": 0.38})
    inp = (tmp_path / "m.inp").read_text()
    assert "11,0.0,0.0,50.0\n12,0.0,0.0,50.0\n" in inp  # ref + rot node after the mesh nodes
    assert "*NSET,NSET=FIX\n1,2,3\n" in inp
    assert "*RIGID BODY,NSET=P0,REF NODE=11,ROT NODE=12" in inp
    assert "*BOUNDARY\nFIX,1,3\n" in inp
    assert inp.count("*STEP") == 2
    assert "11,3,-10.0000\n" in inp  # force on the ref node
    assert "12,2,100.0000\n" in inp  # moment on the rot node
