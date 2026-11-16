import numpy as np
import pytest

from fsa import cli, config

CASES = {"weight": 1, "pull": 2, "twist": 3}


def test_pick_cases():
    assert list(cli.pick_cases(CASES, None)) == ["weight", "pull", "twist"]
    assert list(cli.pick_cases(CASES, "3,weight")) == ["twist", "weight"]
    with pytest.raises(config.UserError, match="out of range"):
        cli.pick_cases(CASES, "4")
    with pytest.raises(config.UserError, match="unknown"):
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
    with pytest.raises(config.UserError, match="share 1"):
        cli.select_bcs(bcs([-1, -1, -1, 6, 1, 1], [4, -1, -1, 10, 1, 1]), surf, sp)
    with pytest.raises(config.UserError, match="no surface nodes"):
        cli.select_bcs(bcs([-1, -1, -1, 1, 1, 1], [20, -1, -1, 30, 1, 1]), surf, sp)


def fake_run(preset):
    """Two nodes in uniaxial x tension: enough for summarise() without meshing or CalculiX."""
    cfg = {
        "name": "p",
        "material": config.material({"preset": preset}),
        "print": {k: config.unit(v) for k, v in config.DEFAULT_PRINT.items()},
        "zones": [],
    }
    ids, xyz, ok = np.array([1, 2]), np.array([[0, 0, 0], [10, 0, 0]], float), np.array([True, True])
    step = {"STRESS": {i: [5.0, 0, 0, 0, 0, 0] for i in ids}, "DISP": {i: [0, 0, 0.1] for i in ids}}
    cases = {"pull": {"hook": (np.zeros(3), np.zeros(3))}}
    return cli.summarise(cfg, cases, [step], ids, xyz, ok, [5.0, 1.5])


def test_printed_part_gets_layer_tension_and_orientation():
    result, fields = fake_run("PETG")
    assert result["best_print_orientation"] == "y"  # x layers carry the 5 MPa; y and z tie at 0, first wins
    assert result["cases"]["pull"]["layer_tension"]["x"]["max"] == 5.0
    assert "pull_layer_x" in fields


def test_milled_part_has_no_layer_output(capsys):
    result, fields = fake_run("AL6061-T6")
    assert "best_print_orientation" not in result and "print_orientations" not in result
    assert "layer_tension" not in result["cases"]["pull"]
    assert not any("_layer_" in k for k in fields)
    cli.print_table(result)
    out = capsys.readouterr().out
    assert "yield 276" in out and "lay-" not in out and "print orientation" not in out


def test_tpu_warning_reaches_summary(capsys):
    result, _ = fake_run("TPU-95A")
    assert "linear" in result["material"]["warning"]
    cli.print_table(result)
    assert "WARNING" in capsys.readouterr().out


def test_bad_input_exits_with_message_not_traceback(tmp_path, capsys):
    toml = tmp_path / "p.toml"
    toml.write_text('geometry = "p.step"\n')  # no material, supports or cases
    with pytest.raises(SystemExit) as e:
        cli.main(["run", str(toml)])
    assert str(e.value).startswith("fsa: material needs a preset")


def test_bugs_still_raise(monkeypatch):
    def boom(*_):
        raise ValueError("a bug, not bad input")

    monkeypatch.setattr(cli, "render_field", boom)
    with pytest.raises(ValueError, match="a bug"):
        cli.main(["render", "runs/x", "case"])
