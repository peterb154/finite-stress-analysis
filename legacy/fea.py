"""Mesh + solve + post-process the monitor adapter.

Usage (inside the container):  python3 fea.py <name> [mesh_size] [fine_size]
Reads cad/<name>.step and cad/<name>_holes.json, writes runs/<name>/.

Frame (from Fusion): x = depth (0 = face against monitor, ~58 = VESA face),
y = horizontal, z = up. Units: mm, N, MPa.
"""
import json
import os
import subprocess
import sys

import gmsh
import numpy as np

# --- Inputs -------------------------------------------------------------
PETG = dict(E=2000.0, nu=0.38, inplane=40.0, interlayer=20.0)  # MPa
FINE_XMAX = float(os.environ.get("FINE_XMAX", "10"))  # fine mesh where x < this
INSERT_R = 2.8          # M4 heat-set insert hole, dia 5.6
SEAT_R = 3.6            # M4 screw head / washer bearing radius
REF = np.array([-40.0, 61.85, 23.85])  # rigid "monitor" ref point (inside monitor)
W = 5.0 * 9.81          # monitor weight, N (HP 32s panel ~4.5 kg, rounded up)


def load_cases():
    """Each case: total force (N) and moment (N*mm) about REF, applied by the monitor."""
    def at(p_minus_ref, f):
        f = np.array(f, float)
        return f, np.cross(np.array(p_minus_ref, float), f)

    wf, wm = np.array([0, 0, -W]), np.zeros(3)
    cases = {}
    cases["1_weight"] = (wf, wm)
    for name, r, f in [
        ("2_push_down_100N", (-20, 0, 0), (0, 0, -100)),     # hand on front, pushing down
        ("3_lift_up_100N", (-20, 0, 0), (0, 0, 100)),        # hand on front, lifting
        ("4_tilt_push_40N_top", (0, 0, 250), (40, 0, 0)),    # push top edge toward wall
        ("5_tilt_pull_40N_top", (0, 0, 250), (-40, 0, 0)),   # pull top edge toward you
        ("6_twist_40N_side", (0, 350, 0), (40, 0, 0)),       # push side edge toward wall
    ]:
        f, m = at(r, f)
        cases[name] = (f + wf, m + wm)
    keep = os.environ.get("CASES")  # e.g. "1,2,5,6"
    if keep:
        cases = {k: v for k, v in cases.items() if k.split("_")[0] in keep.split(",")}
    return cases


BUILD_DIRS = {  # layer-stacking direction for each print orientation
    "flat (plate/spider on bed, layers stack in x)": np.array([1.0, 0, 0]),
    "standing (as installed, layers stack in z)": np.array([0, 0, 1.0]),
    "on side (layers stack in y)": np.array([0, 1.0, 0]),
}


# --- Mesh ---------------------------------------------------------------
def mesh(step, holes, size, fine):
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.option.setString("Geometry.OCCTargetUnit", "MM")
    gmsh.model.occ.importShapes(step)
    gmsh.model.occ.synchronize()
    vols = gmsh.model.getEntities(3)
    if not holes.get("inserts_in_cad"):  # bore out printed threads -> insert holes
        cyls = [(3, gmsh.model.occ.addCylinder(40, h["y"], h["z"], 25, 0, 0, INSERT_R))
                for h in holes["vesa_holes"]]
        gmsh.model.occ.cut(vols, cyls)
        gmsh.model.occ.synchronize()

    # Fine mesh where the plate meets the block (the known failure zone).
    f = gmsh.model.mesh.field
    box = f.add("Box")
    for k, v in dict(VIn=fine, VOut=size, XMin=-1, XMax=FINE_XMAX, YMin=-1, YMax=130,
                     ZMin=-90, ZMax=100, Thickness=4).items():
        f.setNumber(box, k, v)
    f.setAsBackgroundMesh(box)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12)
    gmsh.option.setNumber("Mesh.ElementOrder", 2)
    gmsh.option.setNumber("Mesh.SecondOrderLinear", 0)
    gmsh.option.setNumber("Mesh.SecondOrderLinear", int(os.environ.get("STRAIGHT_TETS", "0")))  # 1 = never-inverted tet10
    gmsh.model.mesh.generate(3)

    tags, xyz, _ = gmsh.model.mesh.getNodes()
    xyz = xyz.reshape(-1, 3)
    _, etags, enodes = gmsh.model.mesh.getElements(3)
    tets = enodes[0].reshape(-1, 10)
    tets = tets[:, [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]]  # gmsh -> CalculiX/VTK tet10 order
    _, _, fnodes = gmsh.model.mesh.getElements(2)
    tris = fnodes[0].reshape(-1, 6)[:, :3]  # surface triangles (corner nodes)
    gmsh.finalize()
    return tags.astype(int), xyz, tets.astype(int), tris.astype(int)


# --- Solve --------------------------------------------------------------
def write_inp(path, ids, xyz, tets, seat, fix, cases, mat):
    rid, rrot = ids.max() + 1, ids.max() + 2
    with open(path, "w") as fp:
        fp.write("*NODE\n")
        for i, p in zip(ids, xyz):
            fp.write(f"{i},{p[0]:.6f},{p[1]:.6f},{p[2]:.6f}\n")
        fp.write(f"{rid},{REF[0]},{REF[1]},{REF[2]}\n{rrot},{REF[0]},{REF[1]},{REF[2]}\n")
        fp.write("*ELEMENT,TYPE=C3D10,ELSET=PART\n")
        for e, t in enumerate(tets, 1):
            fp.write(f"{e}," + ",".join(map(str, t)) + "\n")
        for name, s in (("SEAT", seat), ("FIX", fix)):
            fp.write(f"*NSET,NSET={name}\n")
            for k in range(0, len(s), 12):
                fp.write(",".join(map(str, s[k:k + 12])) + "\n")
        fp.write(f"*MATERIAL,NAME=M\n*ELASTIC\n{mat['E']},{mat['nu']}\n")
        fp.write("*SOLID SECTION,ELSET=PART,MATERIAL=M\n")
        # Monitor chassis is far stiffer than the print: model it as rigid,
        # attached at the 4 load-bearing screw seats.
        fp.write(f"*RIGID BODY,NSET=SEAT,REF NODE={rid},ROT NODE={rrot}\n")
        fp.write("*BOUNDARY\nFIX,1,3\n")  # VESA inserts bonded to arm
        for f, m in cases.values():
            fp.write("*STEP\n*STATIC\n*CLOAD,OP=NEW\n")
            for d in range(3):
                fp.write(f"{rid},{d + 1},{f[d]:.4f}\n{rrot},{d + 1},{m[d]:.4f}\n")
            fp.write("*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n")


def read_frd(path):
    """Return list of (disp, stress) dicts keyed by node id, one per step."""
    steps, cur, block = [], {}, None
    for line in open(path):
        if line.startswith(" -4"):
            block = line.split()[1]
            cur.setdefault(block, {})
        elif line.startswith(" -1") and block:
            nid = int(line[3:13])
            vals = [float(line[13 + 12 * i:25 + 12 * i]) for i in range((len(line.rstrip()) - 13) // 12)]
            cur[block][nid] = vals
        elif line.startswith(" -3"):
            if block == "STRESS":
                steps.append(cur)
                cur = {}
            block = None
    return steps


# --- Post ---------------------------------------------------------------
def stress_measures(s):
    sxx, syy, szz, sxy, syz, szx = s.T
    vm = np.sqrt(0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
                 + 3 * (sxy ** 2 + syz ** 2 + szx ** 2))
    T = np.stack([np.stack([sxx, sxy, szx], -1), np.stack([sxy, syy, syz], -1),
                  np.stack([szx, syz, szz], -1)], -2)
    normal = {k: np.einsum("i,nij,j->n", n, T, n) for k, n in BUILD_DIRS.items()}
    return vm, normal


def render(png, xyz, tris, idx, val, title, vmax, label):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    v = np.clip(val, 0, vmax)
    fig = plt.figure(figsize=(14, 6.5))
    for k, (elev, azim, sub) in enumerate([(20, 35, "block side, from above"),
                                           (-20, 35, "block side, from below"),
                                           (15, 200, "monitor side")]):
        ax = fig.add_subplot(1, 3, k + 1, projection="3d")
        tri_xyz = xyz[idx[tris]]
        col = plt.cm.turbo(v[idx[tris]].mean(1) / vmax)
        pc = Poly3DCollection(tri_xyz, facecolors=col, edgecolors="none")
        ax.add_collection3d(pc)
        ax.set_xlim(-5, 65); ax.set_ylim(-5, 130); ax.set_zlim(-40, 90)
        ax.set_box_aspect((70, 135, 130))
        ax.view_init(elev, azim)
        ax.set_axis_off()
        ax.set_title(sub, fontsize=9)
    sm = plt.cm.ScalarMappable(cmap="turbo", norm=plt.Normalize(0, vmax))
    fig.colorbar(sm, ax=fig.axes, shrink=0.6, label=label)
    fig.suptitle(title)
    fig.savefig(png, dpi=110, bbox_inches="tight")
    plt.close(fig)


def write_vtu(path, xyz, tets, idx, fields):
    with open(path, "w") as fp:
        fp.write('<VTKFile type="UnstructuredGrid" version="0.1">\n<UnstructuredGrid>\n')
        fp.write(f'<Piece NumberOfPoints="{len(xyz)}" NumberOfCells="{len(tets)}">\n<Points>\n')
        fp.write('<DataArray type="Float32" NumberOfComponents="3" format="ascii">\n')
        np.savetxt(fp, xyz, fmt="%.4f")
        fp.write("</DataArray>\n</Points>\n<Cells>\n")
        fp.write('<DataArray type="Int32" Name="connectivity" format="ascii">\n')
        np.savetxt(fp, idx[tets], fmt="%d")
        fp.write('</DataArray>\n<DataArray type="Int32" Name="offsets" format="ascii">\n')
        np.savetxt(fp, np.arange(1, len(tets) + 1) * 10, fmt="%d")
        fp.write('</DataArray>\n<DataArray type="UInt8" Name="types" format="ascii">\n')
        np.savetxt(fp, np.full(len(tets), 24), fmt="%d")
        fp.write("</DataArray>\n</Cells>\n<PointData>\n")
        for name, arr in fields.items():
            nc = 1 if arr.ndim == 1 else arr.shape[1]
            fp.write(f'<DataArray type="Float32" Name="{name}" NumberOfComponents="{nc}" format="ascii">\n')
            np.savetxt(fp, arr.reshape(len(xyz), -1), fmt="%.4g")
            fp.write("</DataArray>\n")
        fp.write("</PointData>\n</Piece>\n</UnstructuredGrid>\n</VTKFile>\n")


def main():
    name = sys.argv[1]
    size = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    fine = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    out = f"runs/{name}"
    os.makedirs(out, exist_ok=True)
    holes = json.load(open(f"cad/{name}_holes.json"))
    mat = PETG

    ids, xyz, tets, tris = mesh(f"cad/{name}.step", holes, size, fine)
    idx = np.zeros(ids.max() + 1, int)
    idx[ids] = np.arange(len(ids))
    surf = np.unique(tris)
    sp = xyz[idx[surf]]

    def near_axis(h, r):
        return np.hypot(sp[:, 1] - h["y"], sp[:, 2] - h["z"]) <= r + 0.05

    load_holes = [h for h in holes["screw_holes"] if h.get("role", "load") == "load"]
    seat = np.unique(np.concatenate([surf[near_axis(h, SEAT_R) & (sp[:, 0] > 0.3)] for h in load_holes]))
    fix = np.unique(np.concatenate([surf[near_axis(h, INSERT_R) & (sp[:, 0] > holes.get("vesa_x0", 40))] for h in holes["vesa_holes"]]))
    print(f"mesh: {len(ids)} nodes, {len(tets)} tet10, seat nodes {len(seat)}, fixed nodes {len(fix)}")

    cases = load_cases()
    write_inp(f"{out}/model.inp", ids, xyz, tets, seat, fix, cases, mat)
    r = subprocess.run(["ccx", "-i", "model"], cwd=out, capture_output=True, text=True)
    if "Job finished" not in r.stdout:
        print(r.stdout[-3000:], r.stderr[-2000:])
        sys.exit(1)
    steps = read_frd(f"{out}/model.frd")

    # Ignore the BC patches themselves (rigid/fixed nodes cause artificial peaks).
    bc = np.zeros(len(ids), bool)
    for s in (seat, fix):
        p = xyz[idx[s]]
        for q in p[:: max(1, len(p) // 400)]:
            bc |= np.linalg.norm(xyz - q, axis=1) < 1.5
    zone = xyz[:, 0] < 10  # plate / block junction

    summary, fields = {}, {}
    for (cname, (f, m)), st in zip(cases.items(), steps):
        s = np.array([st["STRESS"][i][:6] for i in ids])
        u = np.array([st["DISP"][i][:3] for i in ids])
        vm, normal = stress_measures(s)
        ok = ~bc
        row = {"force_N": f.round(1).tolist(), "moment_Nm": (m / 1000).round(2).tolist(),
               "max_disp_mm": float(np.linalg.norm(u, axis=1).max()),
               "vm_max": float(vm[ok].max()), "vm_max_at": xyz[ok][vm[ok].argmax()].round(1).tolist(),
               "vm_max_junction": float(vm[ok & zone].max())}
        for k, sn in normal.items():
            row[f"layer_tension::{k}"] = float(sn[ok].max())
            row[f"layer_tension_at::{k}"] = xyz[ok][sn[ok].argmax()].round(1).tolist()
        summary[cname] = row
        fields[f"{cname}_vm"] = vm
        fields[f"{cname}_layerTension_flat"] = list(normal.values())[0]
        fields[f"{cname}_layerTension_standing"] = list(normal.values())[1]
        fields[f"{cname}_U"] = u

    worst = max(summary, key=lambda c: summary[c]["vm_max"])
    for key, label, lim in [("vm", "von Mises (MPa)", mat["inplane"]),
                            ("layerTension_flat", "tension across layers, FLAT print (MPa)", mat["interlayer"]),
                            ("layerTension_standing", "tension across layers, STANDING print (MPa)", mat["interlayer"])]:
        render(f"{out}/{worst}_{key}.png", xyz, tris, idx, fields[f"{worst}_{key}"],
               f"{name} | {worst} | {label} | limit {lim} MPa", lim, label)
    write_vtu(f"{out}/results.vtu", xyz, tets, idx, fields)
    json.dump({"material": mat, "worst_case": worst, "cases": summary}, open(f"{out}/summary.json", "w"), indent=1)

    print(f"\n{'case':26s} {'vM max':>7s} {'vM junct':>8s} {'flat-x':>7s} {'stand-z':>7s} {'side-y':>7s} {'disp':>6s}")
    for c, r in summary.items():
        lt = [r[k] for k in r if k.startswith("layer_tension::")]
        print(f"{c:26s} {r['vm_max']:7.1f} {r['vm_max_junction']:8.1f} {lt[0]:7.1f} {lt[1]:7.1f} {lt[2]:7.1f} {r['max_disp_mm']:6.2f}")
    print(f"limits: in-plane {mat['inplane']} MPa, interlayer {mat['interlayer']} MPa;  worst case: {worst}")
    print("vM max location:", summary[worst]["vm_max_at"])


if __name__ == "__main__":
    main()
