import numpy as np
import pytest

from fsa import cli, config

CASES = {"weight": 1, "pull": 2, "twist": 3}


def test_pick_cases():
    assert list(cli.pick_cases(CASES, None)) == ["weight", "pull", "twist"]
    assert list(cli.pick_cases(CASES, "3,weight")) == ["twist", "weight"]
    with pytest.raises(SystemExit, match="out of range"):
        cli.pick_cases(CASES, "4")
    with pytest.raises(SystemExit, match="unknown"):
        cli.pick_cases(CASES, "push")


def bcs(fixed_box, hook_box):
    return {
        "fixed": [config.selector({"name": "base", "boxes": [fixed_box]})],
        "paths": {"hook": {**config.selector({"name": "hook", "boxes": [hook_box]}), "ref": np.zeros(3)}},
    }


def test_select_bcs_rejects_overlap_and_empty():
    surf = np.array([10, 11, 12])
    sp = np.array([[0, 0, 0], [5, 0, 0], [9, 0, 0]], float)
    fixed, paths = cli.select_bcs(bcs([-1, -1, -1, 1, 1, 1], [8, -1, -1, 10, 1, 1]), surf, sp)
    assert fixed.tolist() == [10] and paths["hook"][0].tolist() == [12]
    with pytest.raises(SystemExit, match="share 1"):
        cli.select_bcs(bcs([-1, -1, -1, 6, 1, 1], [4, -1, -1, 10, 1, 1]), surf, sp)
    with pytest.raises(SystemExit, match="no surface nodes"):
        cli.select_bcs(bcs([-1, -1, -1, 1, 1, 1], [20, -1, -1, 30, 1, 1]), surf, sp)
