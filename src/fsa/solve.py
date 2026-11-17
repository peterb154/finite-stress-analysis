"""Write a CalculiX deck, run ccx, read the .frd results."""

import os
import subprocess


def write_inp(path, ids, xyz, tets, fixed, paths, cases, mat):
    """`paths`: {name: (node ids, ref point)}. Each load path is a rigid body driven at its ref point."""
    nxt = ids.max() + 1
    refs = {}
    with open(path, "w") as fp:
        fp.write("*NODE\n")
        for i, p in zip(ids, xyz):
            fp.write(f"{i},{p[0]:.6f},{p[1]:.6f},{p[2]:.6f}\n")
        for name, (_, ref) in paths.items():
            refs[name] = (nxt, nxt + 1)
            for n in refs[name]:
                fp.write(f"{n},{ref[0]},{ref[1]},{ref[2]}\n")
            nxt += 2
        fp.write("*ELEMENT,TYPE=C3D10,ELSET=PART\n")
        for e, t in enumerate(tets, 1):
            fp.write(f"{e}," + ",".join(map(str, t)) + "\n")
        sets = {"FIX": fixed, **{f"P{k}": nodes for k, (nodes, _) in enumerate(paths.values())}}
        for name, s in sets.items():
            fp.write(f"*NSET,NSET={name}\n")
            for k in range(0, len(s), 12):
                fp.write(",".join(map(str, s[k : k + 12])) + "\n")
        fp.write(f"*MATERIAL,NAME=M\n*ELASTIC\n{mat['E']},{mat['nu']}\n")
        fp.write("*SOLID SECTION,ELSET=PART,MATERIAL=M\n")
        for k, name in enumerate(paths):
            fp.write(f"*RIGID BODY,NSET=P{k},REF NODE={refs[name][0]},ROT NODE={refs[name][1]}\n")
        fp.write("*BOUNDARY\nFIX,1,3\n")
        for loads in cases.values():
            fp.write("*STEP\n*STATIC\n*CLOAD,OP=NEW\n")
            for name, (f, m) in loads.items():
                rid, rrot = refs[name]
                for d in range(3):
                    fp.write(f"{rid},{d + 1},{f[d]:.4f}\n{rrot},{d + 1},{m[d]:.4f}\n")
            fp.write("*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n")


def run_ccx(workdir):
    # Multithreaded spooles in Debian's CalculiX 2.20 returned wrong stresses. Ubuntu's 2.21 matched on 4
    # threads (monitor-mount examples), but the cause was never found, so keep forcing one thread.
    env = {**os.environ, "CCX_NPROC_EQUATION_SOLVER": "1"}
    r = subprocess.run(["ccx", "-i", "model"], cwd=workdir, capture_output=True, text=True, env=env, check=False)
    if "Job finished" not in r.stdout:
        raise RuntimeError(f"CalculiX failed:\n{r.stdout[-3000:]}\n{r.stderr[-2000:]}")


def read_frd(path):
    """One dict per step: {"DISP": {node: [..]}, "STRESS": {node: [..]}}."""
    steps, cur, block = [], {}, None
    with open(path) as fp:
        lines = fp.readlines()
    for line in lines:
        if line.startswith(" -4"):
            block = line.split()[1]
            cur.setdefault(block, {})
        elif line.startswith(" -1") and block:
            n = (len(line.rstrip()) - 13) // 12
            cur[block][int(line[3:13])] = [float(line[13 + 12 * i : 25 + 12 * i]) for i in range(n)]
        elif line.startswith(" -3"):
            if block == "STRESS":
                steps.append(cur)
                cur = {}
            block = None
    return steps
