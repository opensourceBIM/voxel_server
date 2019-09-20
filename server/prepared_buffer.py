import numpy

def signNotZero(f):
    return 1 if f >= 0. else -1

def normalToOct(normal):
    x = sum(numpy.abs(normal))
    p = normal[0:2] / x
    if normal[2] <= 0.:
        a = (1. - numpy.abs(p[0])) * signNotZero(p[0])
        b = (1. - numpy.abs(p[1])) * signNotZero(p[1])
        p[:] = a, b
    return numpy.int8(p * 127.)

def create(ifn, ofn):
    indices, line_indices, vertices, offsets, line_offsets = [], [], [], [], []

    for l in open(ifn):
        args = l.strip().split(" ")
        a = args[0]
        bs = args[1:]

        if a == "v":
            vertices.extend(map(float, bs))
        elif a == "f":
            bs = list(map(lambda s: s.split("/")[0], bs))
            assert len(bs) == 3
            indices.extend(map(int, bs))
        elif a == "l":
            bs = list(map(lambda s: s.split("/")[0], bs))
            assert len(bs) == 2
            line_indices.extend(map(int, bs))
        elif a in "og":
            offsets.append([len(indices), len(vertices)])
            line_offsets.append([len(line_indices), len(vertices)])
            
    indices_np = numpy.array(indices, dtype=numpy.uint32).reshape((-1, 3)) - 1
    line_indices_np = numpy.array(line_indices, dtype=numpy.uint32).reshape((-1, 2)) - 1
    vertices_np = numpy.array(vertices, dtype=numpy.float32).reshape((-1, 3))
    
    # initialize to (0,0,1) in case we fail to calculate normals (e.g. in case of line vertices)
    normals = numpy.zeros(vertices_np.shape, dtype=numpy.float32)
    normals[:,2] = 1.
    
    for idxs in indices_np:
        tri_vs = vertices_np[idxs]
        e0, e1 = tri_vs[1:] - tri_vs[0]
        c = numpy.cross(e0, e1)
        c /= numpy.linalg.norm(c)
        for id in idxs:
            normals[id] = c

    """
    =========================
    Prepared Buffer Structure
    =========================

    nrObjects      : int
    nrIndices      : int
    (nrLineIndices): 0
    positionsIndex : int
    normalsIndex   : int
    colorsIndex    : int

    align8

    nrObjects      : int
    totalNrIndices : int
    (nrLineIndices): 0
    positionsIndex : int
    normalsIndex   : int
    colorsIndex    : int

    indices        : array<int, totalNrIndices>
    lineIndices    : array<int, nrLineIndices>

    objects : array<struct, nrObjects>
        oid           : long
        startIndex    : int
        (startLI)     : 0
        nrIndices     : int
        (nrLI)        : 0
        nrVertices    : int
        minIndex      : int
        maxIndex      : int
        density       : float
        colorPackSize : int

        colorpack : array<struct, colorPackSize>
            count : int
            color : array<ubyte, 4>
            
        positions : vec<float | short, positionsIndex>
        normals   : vec<byte, normalsIndex>
      
    """

    with open(ofn, "wb") as f:
        numpy.array([len(offsets), indices_np.size * 3, line_indices_np.size * 2, vertices_np.size, normals.size, 0], dtype=numpy.int32).tofile(f)
        # alignment not necessary anymore
        # numpy.array([0], dtype=numpy.int32).tofile(f)
        numpy.array([len(offsets), indices_np.size * 3, line_indices_np.size * 2, vertices_np.size, normals.size, 0], dtype=numpy.int32).tofile(f)
        indices_np.tofile(f)
        line_indices_np.tofile(f)
        for i, (off, voff) in enumerate(offsets):
            numpy.array([0xffff + i], dtype=numpy.int64).tofile(f)
            try:
                next, vnext = offsets[i+1]
            except:
                next = indices_np.size
                vnext = vertices_np.size
            off //= 3
            next //= 3
            
            try:
                min_index, max_index = indices_np[off:next].min(), indices_np[off:next].max()
            except: min_index, max_index = -1, -1
            
            numpy.array([off, 0, next - off, 0, vnext - voff, min_index, max_index], dtype=numpy.int32).tofile(f)
            numpy.array([0.], dtype=numpy.float32).tofile(f)
            numpy.array([1, (vnext - voff) // 3 * 4, 0xff0000ff], dtype=numpy.uint32).tofile(f)
        
        # dequantization happens in the client now for annotations
        # (numpy.int16(vertices_np / 0.05) * 100).tofile(f)
        
        # Viewer expect millimeters
        (vertices_np * 1000.).tofile(f)

        for n in normals.reshape((-1, 3)):
            normalToOct(n).tofile(f)

if __name__ == "__main__":
    import sys
    ifn, ofn = sys.argv[1:]
    create(ifn, ofn)
