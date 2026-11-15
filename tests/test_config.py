from pathlib import Path

import numpy as np
import pytest

from fsa import config

EX = Path(__file__).parent.parent / "examples" / "monitor-mount"


def write(tmp_path, body):
    p = tmp_path / "part.toml"
    p.write_text('step = "x.step"\n' + body)
    return p


MINIMAL = """
[material]
preset = "PLA"
[[fixed]]
name = "base"
boxes = [[0, 0, 0, 10, 10, 1]]
[[load_path]]
name = "hook"
ref = [0, 0, 50]
[[load_path.cylinders]]
point = [5, 5, 0]
axis = [0, 0, 1]
r = 2
[[case]]
name = "hang"
loads = [{ path = "hook", force = [0, 0, -10], at = [10, 0, 50] }]
"""


def test_examples_load():
    for f in ("v5.toml", "v8c.toml"):
        cfg = config.load(EX / f)
        assert len(cfg["cases"]) == 6
        assert cfg["step"].exists()
        assert cfg["material"]["E"] == 2000.0


def test_moment_about_ref(tmp_path):
    cfg = config.load(write(tmp_path, MINIMAL))
    f, m = cfg["cases"]["hang"]["hook"]
    assert np.allclose(f, [0, 0, -10])
    assert np.allclose(m, np.cross([10, 0, 0], [0, 0, -10]))  # 10 mm arm
    assert cfg["name"] == "part"
    assert set(cfg["print"]) == {"x", "y", "z"}


def test_loads_in_one_case_add_up(tmp_path):
    body = MINIMAL.replace(
        'loads = [{ path = "hook", force = [0, 0, -10], at = [10, 0, 50] }]',
        'loads = [{ path = "hook", force = [0, 0, -10] }, { path = "hook", force = [1, 0, 0] }]',
    )
    f, m = config.load(write(tmp_path, body))["cases"]["hang"]["hook"]
    assert np.allclose(f, [1, 0, -10]) and np.allclose(m, 0)


def test_material_override_and_errors(tmp_path):
    assert config.material({"preset": "PETG", "E": 1500})["E"] == 1500.0
    with pytest.raises(ValueError, match="preset"):
        config.material({"E": 1})
    with pytest.raises(ValueError, match="fixed"):
        config.load(write(tmp_path, '[material]\npreset="PLA"\n[[case]]\nname="a"\nloads=[]\n'))


def test_select_cylinder_with_span_and_box():
    sel = config.selector(
        {
            "cylinders": [{"point": [0, 0, 0], "axis": [1, 0, 0], "r": 2, "span": [1, 5]}],
            "boxes": [[10, -1, -1, 11, 1, 1]],
        }
    )
    xyz = np.array([[3, 0, 2], [3, 0, 2.2], [0.5, 0, 1], [6, 0, 0], [10.5, 0, 0]], float)
    assert config.select(sel, np.arange(5), xyz).tolist() == [0, 4]


def test_near_bc_is_exact():
    from fsa import post

    xyz = np.array([[0, 0, 0], [1.4, 0, 0], [1.6, 0, 0], [10, 0, 0], [10, 1.2, 0]], float)
    bc = np.array([[0, 0, 0], [10, 0, 0]], float)
    assert post.near_bc(xyz, bc).tolist() == [True, True, False, True, True]
