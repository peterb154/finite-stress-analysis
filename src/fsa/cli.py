"""fsa: stress-check a 3D-printed part.

fsa run part.toml [--coarse] [--cases weight,pull]
fsa render runs/<name> <case> [--field vm|layer_<orientation>] [--max MPa]
fsa compare runs/a runs/b [--case <case>] [--field vm] [--out compare.png]
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from . import config, post, render, solve
from .mesh import mesh


def run(args):
    t0 = time.time()
    cfg = config.load(args.config)
    size, fine = cfg["mesh"]["size"], cfg["mesh"]["fine"]
    if args.coarse:
        size, fine = max(size, 6.0), max(fine, 4.0)
    cases = pick_cases(cfg["cases"], args.cases)
    out = Path(args.out) if args.out else cfg["dir"] / "runs" / cfg["name"]
    out.mkdir(parents=True, exist_ok=True)
    for old in [*out.glob("*_vm.png"), *out.glob("*_layer_*.png"), out / "summary.json", out / "results.vtu"]:
        old.unlink(missing_ok=True)  # don't leave heat maps from an earlier run next to new results

    ids, xyz, tets, tris = mesh(cfg, size, fine)
    idx = np.zeros(ids.max() + 1, int)
    idx[ids] = np.arange(len(ids))
    surf = np.unique(tris)
    fixed, paths = select_bcs(cfg, surf, xyz[idx[surf]])
    print(
        f"mesh {size:g}/{fine:g} mm: {len(ids)} nodes, {len(tets)} tet10, fixed nodes {len(fixed)}, "
        + ", ".join(f"{n} nodes {len(v[0])}" for n, v in paths.items())
    )

    solve.write_inp(out / "model.inp", ids, xyz, tets, fixed, paths, cases, cfg["material"])
    solve.run_ccx(out)
    steps = solve.read_frd(out / "model.frd")
    if len(steps) != len(cases):
        raise RuntimeError(f"CalculiX wrote {len(steps)} result steps for {len(cases)} cases: see {out}/model.dat")

    bc_nodes = np.concatenate([fixed, *(v[0] for v in paths.values())])
    ok = ~post.near_bc(xyz, xyz[idx[bc_nodes]])
    result, fields = summarise(cfg, cases, steps, ids, xyz, ok, [size, fine])
    (out / "summary.json").write_text(json.dumps(result, indent=1))
    post.write_vtu(out / "results.vtu", xyz, idx[tets], fields)
    mat, worst = cfg["material"], result["worst_case"]
    maps = [("vm", mat["inplane"])]
    if mat["printed"]:
        maps.append((f"layer_{result['best_print_orientation']}", mat["interlayer"]))
    for key, lim in maps:
        render.render(
            out / f"{worst}_{key}.png",
            f"{cfg['name']} | {worst} | {key}",
            xyz,
            idx[tets],
            fields[f"{worst}_{key}"],
            ok,
            lim,
        )
    print_table(result)
    print(f"wrote {out}/ in {time.time() - t0:.0f} s")


def summarise(cfg, cases, steps, ids, xyz, ok, mesh_mm):
    """summary.json contents + per-node fields. Layer tension only for printed materials."""
    mat = cfg["material"]
    orients = cfg["print"] if mat["printed"] else {}
    summary, fields = {}, {"bc_excluded": (~ok).astype(float)}
    for (cname, loads), st in zip(cases.items(), steps):
        s = np.array([st["STRESS"][i][:6] for i in ids])
        u = np.array([st["DISP"][i][:3] for i in ids])
        vm = post.von_mises(s)
        row = {
            "loads": {
                p: {"force_N": f.round(1).tolist(), "moment_Nmm": m.round(0).tolist()} for p, (f, m) in loads.items()
            },
            "max_disp_mm": round(float(np.linalg.norm(u, axis=1).max()), 3),
        }
        row["vm_max"], row["vm_max_at"] = post.peak(vm, xyz, ok)
        for o, n in orients.items():
            lt = post.normal_stress(s, n)
            mx, at = post.peak(lt, xyz, ok)
            row.setdefault("layer_tension", {})[o] = {"max": mx, "at": at}
            fields[f"{cname}_layer_{o}"] = lt
        for z in cfg["zones"]:
            lo, hi = np.array(z["box"], float).reshape(2, 3)
            inz = ok & ((xyz >= lo) & (xyz <= hi)).all(1)
            row.setdefault("zones", {})[z["name"]] = float(vm[inz].max()) if inz.any() else None
        summary[cname] = row
        fields[f"{cname}_vm"] = vm
        fields[f"{cname}_U"] = u

    result = {
        "name": cfg["name"],
        "material": mat,
        "mesh_mm": mesh_mm,
        "worst_case": max(summary, key=lambda c: summary[c]["vm_max"]),
    }
    if orients:
        result["best_print_orientation"] = min(
            orients, key=lambda o: max(r["layer_tension"][o]["max"] for r in summary.values())
        )
        result["print_orientations"] = {k: v.tolist() for k, v in orients.items()}
    result["cases"] = summary
    return result, fields


def select_bcs(cfg, surf, sp):
    """Surface nodes for the fixed supports and each load path. They must be non-empty and disjoint."""
    fixed = np.unique(np.concatenate([config.select(s, surf, sp) for s in cfg["fixed"]]))
    paths = {n: (np.unique(config.select(p, surf, sp)), p["ref"]) for n, p in cfg["paths"].items()}
    groups = {"fixed": fixed, **{n: v[0] for n, v in paths.items()}}
    for n, nodes in groups.items():
        if len(nodes) == 0:
            raise config.UserError(
                f"'{n}' selected no surface nodes: check its cylinders/boxes against the STEP coordinates"
            )
    names = list(groups)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            both = np.intersect1d(groups[a], groups[b])
            if len(both):
                raise config.UserError(
                    f"'{a}' and '{b}' share {len(both)} surface nodes: a node can't be both. Shrink one."
                )
    return fixed, paths


def pick_cases(cases, sel):
    if not sel:
        return cases
    names = list(cases)
    keep = []
    for s in sel.split(","):
        if s.isdigit() and not 1 <= int(s) <= len(names):
            raise config.UserError(f"case number {s} out of range 1..{len(names)}")
        keep.append(names[int(s) - 1] if s.isdigit() else s)
    unknown = [k for k in keep if k not in cases]
    if unknown:
        raise config.UserError(f"unknown case(s) {unknown}; have {names}")
    return {k: cases[k] for k in keep}


def print_table(r):
    mat, orients = r["material"], list(r.get("print_orientations", {}))
    print(f"\n{'case':28s} {'vM max':>7s} " + "".join(f" {'lay-' + o:>9s}" for o in orients) + f" {'disp mm':>8s}")
    for c, row in r["cases"].items():
        lt = "".join(f" {row['layer_tension'][o]['max']:9.1f}" for o in orients)
        print(f"{c:28s} {row['vm_max']:7.1f}{lt} {row['max_disp_mm']:8.2f}")
    w = r["cases"][r["worst_case"]]
    worst = (
        f"worst case: {r['worst_case']} (peak {w['vm_max']:.1f} MPa at {w['vm_max_at']}, "
        f"margin {mat['inplane'] / w['vm_max']:.1f}x)"
    )
    if orients:
        print(f"limits: in-plane {mat['inplane']:g} MPa, across layers {mat['interlayer']:g} MPa")
        print(f"{worst}; best print orientation: {r['best_print_orientation']}")
    else:
        print(f"limit: yield {mat['inplane']:g} MPa (not printed: no layer check)")
        print(worst)
    if mat.get("warning"):
        print(f"WARNING: {mat['warning']}")


def load_run(d):
    d = Path(d)
    xyz, tets, fields = post.read_vtu(d / "results.vtu")
    return json.loads((d / "summary.json").read_text()), xyz, tets, fields


def render_field(d, case, field, vmax=None):
    s, xyz, tets, fields = load_run(d)
    key = f"{case}_{field}"
    if key not in fields:
        raise config.UserError(f"no field {key}; have {sorted(k for k in fields if k.startswith(case))}")
    if vmax is None:
        vmax = s["material"]["inplane" if field == "vm" else "interlayer"]
    out = Path(d) / f"{key}.png"
    render.render(out, f"{s['name']} | {case} | {field}", xyz, tets, fields[key], fields["bc_excluded"] < 0.5, vmax)
    print("wrote", out)
    return out, s


def compare(args):
    runs = [json.loads((Path(d) / "summary.json").read_text()) for d in args.runs]
    case = args.case or runs[0]["worst_case"]
    pngs, titles = [], []
    for d, s in zip(args.runs, runs):
        png, _ = render_field(d, case, args.field, args.max)
        pngs.append(png)
        titles.append(f"{s['name']}: peak {s['cases'][case]['vm_max']:.1f} MPa")
    render.side_by_side(args.out, pngs, titles)
    print("wrote", args.out)
    common = [c for c in runs[0]["cases"] if all(c in r["cases"] for r in runs)]
    print("\n| case | " + " | ".join(f"{r['name']} vM / disp" for r in runs) + " |")
    print("|---|" + "---|" * len(runs))
    for c in common:
        print(
            f"| {c} | "
            + " | ".join(f"{r['cases'][c]['vm_max']:.1f} MPa / {r['cases'][c]['max_disp_mm']:.2f} mm" for r in runs)
            + " |"
        )


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fsa", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="mesh, solve and summarise a part.toml")
    r.add_argument("config")
    r.add_argument("--coarse", action="store_true", help="quick low-res mesh (~10 s) to check the setup")
    r.add_argument("--cases", help="comma-separated case names or 1-based numbers")
    r.add_argument("--out", help="output folder (default: runs/<name> next to the config)")
    r.set_defaults(fn=run)
    d = sub.add_parser("render", help="heat map of one field from a finished run")
    d.add_argument("run_dir")
    d.add_argument("case")
    d.add_argument("--field", default="vm", help="vm or layer_<orientation>")
    d.add_argument("--max", type=float, help="colour-scale max, MPa (default: material limit)")
    d.set_defaults(fn=lambda a: render_field(a.run_dir, a.case, a.field, a.max))
    c = sub.add_parser("compare", help="side-by-side heat maps + table for several runs")
    c.add_argument("runs", nargs="+")
    c.add_argument("--case")
    c.add_argument("--field", default="vm")
    c.add_argument("--max", type=float)
    c.add_argument("--out", default="compare.png")
    c.set_defaults(fn=compare)
    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except (config.UserError, FileNotFoundError) as e:  # bad input: the message says what to fix
        sys.exit(f"fsa: {e}")
