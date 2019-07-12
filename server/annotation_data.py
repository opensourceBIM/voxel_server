import json
import numpy
import bisect
import operator
import ifcopenshell

def create(ifc, obj, ofn):

    f = ifcopenshell.open(ifc)
    ss = sorted(f.by_type("IfcBuildingStorey"), key=operator.attrgetter("Elevation"))
    elevations = list(map(operator.attrgetter("Elevation"), ss))

    objects = []

    for l in open(obj):
        args = l.strip().split(" ")
        a = args[0]
        bs = args[1:]
        if a == "v":
            objects[-1]["storey"] = min(objects[-1]["storey"], float(bs[2]))
        elif a == "g":
            objects.append({"name": bs[0], "storey": float("inf")})

    for o in objects:
        idx = bisect.bisect_left(elevations, o["storey"])
        idx = max(idx - 1, 0)
        o["storey"] = ss[idx].GlobalId

    json.dump(objects, open(ofn, "w"))

if __name__ == "__main__":
    import sys
    create(*sys.argv[1:])
