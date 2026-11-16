import numpy as np
import pytest

from fsa import config, post


def test_vtu_round_trip(tmp_path):
    xyz = np.random.default_rng(1).random((10, 3)) * 100
    tets = np.arange(10).reshape(1, 10)
    fields = {"a_vm": np.arange(10.0), "a_U": np.ones((10, 3))}
    post.write_vtu(tmp_path / "r.vtu", xyz, tets, fields)
    xyz2, tets2, f2 = post.read_vtu(tmp_path / "r.vtu")
    assert np.allclose(xyz2, xyz, atol=1e-4)
    assert (tets2 == tets).all()
    assert np.allclose(f2["a_vm"], fields["a_vm"])
    assert len(f2["a_U"]) == 30  # vectors come back flat


def test_von_mises_uniaxial_and_layer_tension():
    s = np.array([[10.0, 0, 0, 0, 0, 0]])
    assert np.allclose(post.von_mises(s), 10)
    assert np.allclose(post.normal_stress(s, np.array([1.0, 0, 0])), 10)
    assert np.allclose(post.normal_stress(s, np.array([0, 0, 1.0])), 0)


def test_peak_skips_excluded_nodes_and_fails_when_all_excluded():
    xyz = np.eye(3)
    assert post.peak(np.array([9.0, 2, 1]), xyz, np.array([False, True, True])) == (2.0, [0.0, 1.0, 0.0])
    with pytest.raises(config.UserError, match="too much"):
        post.peak(np.ones(3), xyz, np.zeros(3, bool))
