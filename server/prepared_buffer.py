import numpy

def create(ifn, ofn):

    indices, vertices, offsets = [], [], []

    for l in open(ifn):
        args = l.strip().split(" ")
        a = args[0]
        bs = args[1:]
        if a == "v":
            vertices.extend(map(float, bs))
        elif a == "f":
            indices.extend(map(int, bs))
        elif a == "g":
            offsets.append([len(indices), len(vertices)])
            
    indices_np = numpy.array(indices, dtype=numpy.uint32).reshape((-1, 3)) - 1
    vertices_np = numpy.array(vertices, dtype=numpy.float32).reshape((-1, 3))
    normals = numpy.empty(vertices_np.shape, dtype=numpy.float32)

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
    positionsIndex : int
    normalsIndex   : int
    colorsIndex    : int

    align8

    nrObjects      : int
    totalNrIndices : int
    positionsIndex : int
    normalsIndex   : int
    colorsIndex    : int

    indices        : array<int, totalNrIndices>

    objects : array<struct, nrObjects>
        oid           : long
        startIndex    : int
        nrIndices     : int
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
        numpy.array([len(offsets), indices_np.size, vertices_np.size, normals.size, 0], dtype=numpy.int32).tofile(f)
        numpy.array([0], dtype=numpy.int32).tofile(f)
        numpy.array([len(offsets), indices_np.size, vertices_np.size, normals.size, 0], dtype=numpy.int32).tofile(f)
        indices_np.tofile(f)
        for i, (off, voff) in enumerate(offsets):
            numpy.array([0xffff + i], dtype=numpy.int64).tofile(f)
            try:
                next, vnext = offsets[i+1]
            except:
                next = indices_np.size
                vnext = vertices_np.size
            off //= 3
            next //= 3
            numpy.array([off, next - off, vnext - voff, indices_np[off:next].min(), indices_np[off:next].max()], dtype=numpy.int32).tofile(f)
            numpy.array([0.], dtype=numpy.float32).tofile(f)
            numpy.array([1, (vnext - voff) // 3 * 4, 0xff0000ff], dtype=numpy.uint32).tofile(f)
        
        # dequantization happens in the client now for annotations
        # (numpy.int16(vertices_np / 0.05) * 100).tofile(f)
        
        # Viewer expect millimeters
        (vertices_np * 1000.).tofile(f)
        
        numpy.int8(normals * 128).tofile(f)
            