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

# ifn, ofn
# or
# ofn, ifn0, color0, iffn1, color1, ...    
def create(*args):
    if len(args) == 2:
        ifn, ofn = args
        input_pairs = [[ifn, 0xff0000ff]]
    else:
        ofn = args[0]
        rest = args[1:]
        assert len(rest) % 2 == 0
        def color(s):
            if len(s) == 3:
                r, g, b = s;
                s = "".join((b, b, g, g, r, r))
            if len(s) == 6:
                s = "ff" + s
            return int(s, 16)
        input_pairs = zip(rest[::2], map(color, rest[1::2]))        
        
    index_count, line_index_count, vertex_count = 0, 0, 0
    offsets = []
    line_offsets = []
    indices_np_total, line_indices_np_total, vertices_np_total, normals_np_total = None, None, None, None

    with open(ofn, "wb") as f:
    
        index_offset = 0
    
        for ifn, clr in input_pairs:
            # print(ifn, hex(clr))
        
            indices, line_indices, vertices = [], [], []
        
            for l in open(ifn):
                args = l.strip().split(" ")
                a = args[0]
                bs = args[1:]

                if a == "v":
                    vertices.extend(map(float, bs))
                    vertex_count += 3
                elif a == "f":
                    assert len(bs) == 3
                    indices.extend(map(lambda s: int(s.split("/")[0]), bs))
                    index_count += 3
                elif a == "l":
                    assert len(bs) == 2
                    line_indices.extend(map(lambda s: int(s.split("/")[0]), bs))
                    line_index_count += 2
                elif a in "og":
                    # if bs == ["component1"]: break
                    
                    offsets.append([index_count, vertex_count, clr])
                    line_offsets.append([line_index_count, vertex_count, clr])
                    
            indices_np = numpy.array(indices, dtype=numpy.uint32).reshape((-1, 3)) - 1
            line_indices_np = numpy.array(line_indices, dtype=numpy.uint32).reshape((-1, 2)) - 1
            vertices_np = numpy.array(vertices, dtype=numpy.float32).reshape((-1, 3))
            
            indices[:] = []
            line_indices[:] = []
            vertices[:] = []
            
            # initialize to (0,0,1) in case we fail to calculate normals (e.g. in case of line vertices)
            normals = numpy.zeros(vertices_np.shape, dtype=numpy.float32)
            normals[:,2] = 1.
            
            n = 0
            for idxs in indices_np:
                if n % 2 == 0:
                    # We use the fact that in our case of voxels always quads are emitted
                    tri_vs = vertices_np[idxs]
                    e0, e1 = tri_vs[1:] - tri_vs[0]
                    c = numpy.cross(e0, e1)
                    # no sqrt
                    # c /= numpy.linalg.norm(c)
                    c = numpy.copysign(numpy.abs(c) > 0.001, c)
                for id in idxs:
                    normals[id] = c
                n += 1

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
            
            if indices_np_total is None:
                indices_np_total = indices_np
                line_indices_np_total = line_indices_np
                vertices_np_total = vertices_np
                normals_np_total = normals
            else:
                indices_np += index_offset
                line_indices_np += index_offset
                
                indices_np_total = numpy.vstack((indices_np_total, indices_np))
                line_indices_np_total = numpy.vstack((line_indices_np_total, line_indices_np))
                vertices_np_total = numpy.vstack((vertices_np_total, vertices_np))
                normals_np_total = numpy.vstack((normals_np_total, normals))
                
            index_offset += vertices_np.shape[0]
                
        # print([len(offsets), indices_np_total.size, line_indices_np_total.size, vertices_np_total.size, normals_np_total.size, 0])
        # print(offsets)
        
        numpy.array([len(offsets), indices_np_total.size, line_indices_np_total.size, vertices_np_total.size, normals_np_total.size, 0], dtype=numpy.int32).tofile(f)
        # alignment not necessary anymore
        # numpy.array([0], dtype=numpy.int32).tofile(f)
        numpy.array([len(offsets), indices_np_total.size, line_indices_np_total.size, vertices_np_total.size, normals_np_total.size, 0], dtype=numpy.int32).tofile(f)        
        
        indices_np_total.tofile(f)
        line_indices_np_total.tofile(f)
        
        nrColors = vertices_np_total.size * 4 // 3
        iVerts = 0
        iColors = 0
        
        for i, (off, voff, clr) in enumerate(offsets):
            # nb OID set to zero, assign in viewer
            numpy.array([0], dtype=numpy.int64).tofile(f)
            try:
                next, vnext, _ = offsets[i+1]
            except IndexError as e:
                next = indices_np_total.size
                vnext = vertices_np_total.size
            off //= 3
            next //= 3
            
            min_index, max_index = indices_np_total[off:next].min(), indices_np_total[off:next].max()
            
            iVerts += vnext - voff
            iColors += (vnext - voff) // 3 * 4
            
            vs = vertices_np_total[min_index:max_index+1]
            # print(hex(clr))
            # print("i", off, "-", next)
            # print("v", min_index, "-" , max_index)
            # print(numpy.min(vs, axis=0))
            # print(numpy.max(vs, axis=0))
            
            numpy.array([off, 0, next - off, 0, vnext - voff, min_index, max_index], dtype=numpy.int32).tofile(f)
            numpy.array([0.], dtype=numpy.float32).tofile(f)
            numpy.array([1, (vnext - voff) // 3 * 4, clr], dtype=numpy.uint32).tofile(f)
            
        assert iColors == nrColors
        
        # dequantization happens in the client now for annotations
        # (numpy.int16(vertices_np_total / 0.05) * 100).tofile(f)
        
        # Viewer expect millimeters
        (vertices_np_total * 1000.).tofile(f)
        
        # Normals no longer oct encoded
        # for n in normals.reshape((-1, 3)):
        #     normalToOct(n).tofile(f)
        
        numpy.int8(normals_np_total * 128).tofile(f)

if __name__ == "__main__":
    import sys
    create(*sys.argv[1:])
