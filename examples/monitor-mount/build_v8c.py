"""Build 'MonitorMount v7' in the open Fusion design (run via the Fusion MCP script tool).

Re-running deletes and rebuilds the v7 component. Edit the parameters below and re-run.
Frame (same as v5): x = depth from pocket floor, y = width, z = up. Units: mm.
The HP plate+tabs and the spider outline are copied from v5's body so their
interface geometry stays exactly what already fits.
"""
import math

import adsk.core
import adsk.fusion

# --- Parameters (mm / deg) ---------------------------------------------
PLATE_W, PLATE_H, PLATE_T = 123.7, 47.7, 3.0   # HP plate (copied from v5)
BACK_T = 9.0  # plate + backing thickness (x = 0 .. BACK_T)
FLOOR = 5.0            # screw seat floor (M4x10 SHCS -> ~5 mm thread engagement)
CB_R = 4.0             # counterbore radius (M4 SHCS head 7 mm)
ROCK_DEG = 15.0        # install rock angle the top slope is cut for
SPIDER_X = 37.0        # spider back face (pocket wall 33.3 + rock clearance)
SPIDER_T = 10.0        # spider thickness (v5: 10)
SPIDER_DROP = 38.65    # move spider down so its top is level with the tabs
BLOCK_Y = (33.85, 89.85)  # block width (v7: 62.5 -> 50 mm)
BLOCK_ZMIN = -25.0
CORE_R = 17.0  # lightening bore through block from the spider side (0 = none)
CORE_Z = 12.0          # bore centre height
CORE_X0 = BACK_T + 3.0  # bore stops here, leaving the backing intact
FILLET_R = 4.0
INSERT_R = 2.8         # M4 heat-set insert hole (dia 5.6)
LOAD = [(8.55, 42.95), (115.15, 42.95), (8.55, 6.95), (115.15, 6.95)]
REG = [(9.75, 14.35), (113.95, 14.35)]
V5_SPIDER_X0, V5_VESA_C = 48.0, (61.85, 23.85)

NAME = "MonitorMount v8c"  # same component name; rebuild replaces it
P = adsk.core.Point3D.create


def V(mm):
    return adsk.core.ValueInput.createByReal(mm / 10)


def run(_context: str):
    app = adsk.core.Application.get()
    d = adsk.fusion.Design.cast(app.activeProduct)
    root = d.rootComponent
    for o in list(root.occurrences):
        if o.component.name == NAME:
            o.deleteMe()
    v5 = [o for o in root.allOccurrences if o.component.name == "MonitorIterface"][0]
    v5body = v5.bRepBodies.item(0)
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    comp = occ.component
    comp.name = NAME
    tb = adsk.fusion.TemporaryBRepManager.get()

    def box(x0, x1, y0, y1, z0, z1):
        c = P((x0 + x1) / 20, (y0 + y1) / 20, (z0 + z1) / 20)
        ob = adsk.core.OrientedBoundingBox3D.create(
            c, adsk.core.Vector3D.create(1, 0, 0), adsk.core.Vector3D.create(0, 1, 0),
            (x1 - x0) / 10, (y1 - y0) / 10, (z1 - z0) / 10)
        return tb.createBox(ob)

    # 1. copy HP plate (+tabs) and spider from v5 into a base feature
    plate = tb.copy(v5body)
    tb.booleanOperation(plate, box(-1, PLATE_T, -10, 140, -10, 70), adsk.fusion.BooleanTypes.IntersectionBooleanType)
    spider = tb.copy(v5body)
    tb.booleanOperation(spider, box(V5_SPIDER_X0, V5_SPIDER_X0 + SPIDER_T + 1, -10, 140, -60, 110),
                        adsk.fusion.BooleanTypes.IntersectionBooleanType)
    m = adsk.core.Matrix3D.create()
    m.translation = adsk.core.Vector3D.create((SPIDER_X - V5_SPIDER_X0) / 10, 0, -SPIDER_DROP / 10)
    tb.transform(spider, m)
    bf = comp.features.baseFeatures.add()
    bf.startEdit()
    comp.bRepBodies.add(plate, bf)
    comp.bRepBodies.add(spider, bf)
    bf.finishEdit()
    bf.name = "v7 copied plate + spider"

    def plane(x, name):
        pi = comp.constructionPlanes.createInput()
        pi.setByOffset(comp.yZConstructionPlane, V(x))
        p = comp.constructionPlanes.add(pi)
        p.name = name
        p.isLightBulbOn = False
        return p

    def sk(pl, name):
        s = comp.sketches.add(pl)
        s.name = name
        s.isVisible = False
        return s

    def sp(s, x, y, z):
        return s.modelToSketchSpace(P(x / 10, y / 10, z / 10))

    def rect(s, x, y0, z0, y1, z1):
        return s.sketchCurves.sketchLines.addTwoPointRectangle(sp(s, x, y0, z0), sp(s, x, y1, z1))

    def extrude(s, dist, op, name, profiles=None, bodies=None):
        coll = adsk.core.ObjectCollection.create()
        for p in (profiles or s.profiles):
            coll.add(p)
        ei = comp.features.extrudeFeatures.createInput(coll, op)
        ei.setDistanceExtent(False, V(dist))
        if bodies:
            ei.participantBodies = bodies
        f = comp.features.extrudeFeatures.add(ei)
        f.name = name
        return f

    J, C = adsk.fusion.FeatureOperations.JoinFeatureOperation, adsk.fusion.FeatureOperations.CutFeatureOperation
    NB = adsk.fusion.FeatureOperations.NewBodyFeatureOperation

    # 2. backing plate x = PLATE_T .. BACK_T over the full plate outline (r3 corners)
    s = sk(plane(PLATE_T, "v7 plate back"), "v7 backing")
    r = rect(s, PLATE_T, 0, 0, PLATE_W, PLATE_H)
    for i in range(4):
        a, b = r.item(i), r.item((i + 1) % 4)
        s.sketchCurves.sketchArcs.addFillet(a, a.endSketchPoint.geometry, b, b.startSketchPoint.geometry, 0.3)
    main = extrude(s, BACK_T - PLATE_T, NB, "v7 Backing").bodies.item(0)

    # 3. block: upper part from the plate to the spider, lower part (below plate) from BACK_T
    s = sk(comp.constructionPlanes.item(comp.constructionPlanes.count - 1), "v7 block upper")
    rect(s, PLATE_T, BLOCK_Y[0], 0, BLOCK_Y[1], PLATE_H)
    extrude(s, SPIDER_X - PLATE_T + 0.5, J, "v7 Block upper", bodies=[main])
    s = sk(plane(BACK_T, "v7 backing face"), "v7 block lower")
    rect(s, BACK_T, BLOCK_Y[0], BLOCK_ZMIN, BLOCK_Y[1], 0.0)
    extrude(s, SPIDER_X - BACK_T + 0.5, J, "v7 Block lower", bodies=[main])

    # 4. rock-clearance slope on top of backing + block (tabs/plate untouched)
    s = sk(comp.xZConstructionPlane, "v7 rock slope")
    t = math.tan(math.radians(ROCK_DEG))
    pts = [(PLATE_T, PLATE_H - PLATE_T * t), (SPIDER_X + 0.5, PLATE_H - (SPIDER_X + 0.5) * t),
           (SPIDER_X + 0.5, PLATE_H + 20), (PLATE_T, PLATE_H + 20)]
    L = s.sketchCurves.sketchLines
    q = [s.modelToSketchSpace(P(x / 10, 0, z / 10)) for x, z in pts]
    for i in range(4):
        L.addByTwoPoints(q[i], q[(i + 1) % 4])
    ei = comp.features.extrudeFeatures.createInput(s.profiles.item(0), C)
    ei.setSymmetricExtent(V(200), True)
    ei.participantBodies = [main]
    comp.features.extrudeFeatures.add(ei).name = "v7 Rock slope"

    # 5. combine everything into one body
    tools = adsk.core.ObjectCollection.create()
    for b in comp.bRepBodies:
        if b != main:
            tools.add(b)
    ci = comp.features.combineFeatures.createInput(main, tools)
    ci.operation = J
    comp.features.combineFeatures.add(ci).name = "v7 Combine"
    body = comp.bRepBodies.item(0)
    body.name = "MonitorMount v7"

    # 6. counterbores (top ones slotted out through the top), screw + registration holes
    s = sk(comp.constructionPlanes.itemByName("v7 backing face"), "v7 counterbores")
    for y, z in LOAD:
        s.sketchCurves.sketchCircles.addByCenterRadius(sp(s, BACK_T, y, z), CB_R / 10)
        if z > PLATE_H / 2:
            rect(s, BACK_T, y - CB_R, z, y + CB_R, PLATE_H + 6)
    extrude(s, -(BACK_T - FLOOR), C, "v7 Counterbores", bodies=[body])
    s = sk(comp.constructionPlanes.itemByName("v7 backing face"), "v7 holes")
    for y, z in LOAD:
        s.sketchCurves.sketchCircles.addByCenterRadius(sp(s, BACK_T, y, z), 0.20)
    for y, z in REG:
        s.sketchCurves.sketchCircles.addByCenterRadius(sp(s, BACK_T, y, z), 0.205)
    extrude(s, -(BACK_T + 1), C, "v7 Screw + reg holes", bodies=[body])

    # 7. heat-set insert holes through the spider
    s = sk(plane(SPIDER_X - 1, "v7 insert plane"), "v7 inserts")
    cy, cz = V5_VESA_C[0], V5_VESA_C[1] - SPIDER_DROP
    for dy in (-50, 50):
        for dz in (-50, 50):
            s.sketchCurves.sketchCircles.addByCenterRadius(sp(s, SPIDER_X - 1, cy + dy, cz + dz), INSERT_R / 10)
    extrude(s, SPIDER_T + 2, C, "v7 Insert holes", bodies=[body])

    # 7b. lightening bore (vertical when printed spider-face-down: no supports)
    if CORE_R > 0:
        s = sk(plane(CORE_X0, "v7 core plane"), "v7 core")
        s.sketchCurves.sketchCircles.addByCenterRadius(sp(s, CORE_X0, 61.85, CORE_Z), CORE_R / 10)
        extrude(s, SPIDER_X - CORE_X0 - 2.0, C, "v7 Core bore", bodies=[body])  # stops 2 mm short of the spider

    # 8. fillets where the block meets the backing and the spider
    def on_x(e, x):
        b = e.boundingBox
        return abs(b.minPoint.x * 10 - x) < 0.01 and abs(b.maxPoint.x * 10 - x) < 0.01

    def block_edge(e):
        mp = e.pointOnEdge
        y, z = mp.y * 10, mp.z * 10
        return (abs(y - BLOCK_Y[0]) < 0.05 or abs(y - BLOCK_Y[1]) < 0.05
                or abs(z - BLOCK_ZMIN) < 0.05 or abs(z) < 0.05 or z > 30) and BLOCK_Y[0] - 0.1 < y < BLOCK_Y[1] + 0.1

    edges = adsk.core.ObjectCollection.create()
    for e in body.edges:
        if (on_x(e, BACK_T) or on_x(e, SPIDER_X)) and block_edge(e):
            edges.add(e)
    if edges.count:
        fi = comp.features.filletFeatures.createInput()
        fi.edgeSetInputs.addConstantRadiusEdgeSet(edges, V(FILLET_R), True)
        comp.features.filletFeatures.add(fi).name = "v7 Block fillets"

    v5.isLightBulbOn = False
    for o in root.occurrences:
        if o.component.name.startswith("MonitorMount v") and o.component.name != NAME:
            o.isLightBulbOn = False
    for o in root.occurrences:
        if o.component.name == "WallMount":
            o.isLightBulbOn = False
    bb = body.boundingBox
    print("v7 built: bodies", comp.bRepBodies.count, "fillet edges", edges.count,
          "volume cm3 %.1f" % body.volume,
          "bbox mm", [round(v * 10, 1) for v in (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z,
                                                 bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)])
    print("v5 volume cm3 %.1f" % v5body.volume)
